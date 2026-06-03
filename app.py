# Recouvr SaaS - v2.1 Gemini
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, date
import resend
import json
import os
import urllib.request

app = Flask(__name__)
app.secret_key = "recouvr-secret-2024"

resend.api_key = "re_JCPxxYWh_2J4bmCdfa5VoLp6kQ5SkVeA5"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6KrJIfdKTUFRRVN2vvJK7NMRW2L32-y5s3twmTqwVAENg")

debiteurs = []
factures  = []
email_log = []

def generate_email_gemini(debiteur, facture, company):
    prompt = f"""Tu es un expert en recouvrement B2B en Afrique de l'Ouest.
Génère un email de relance professionnel.
Créancier : {company}
Débiteur : {debiteur['name']} ({debiteur['company']})
Montant dû : {facture['amount']:,.0f} FCFA
Référence : {facture['ref']}
Jours de retard : {facture['days_late']}
Lien paiement : https://recouvr-saas.onrender.com/payer/{facture['ref']}

Réponds UNIQUEMENT en JSON sans backticks :
{{"subject": "objet email", "body_html": "corps HTML avec balises p strong br"}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    raw = result["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(raw.replace("```json","").replace("```","").strip())

@app.route("/", methods=["GET", "POST"])
def onboarding():
    if session.get("email"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        session["company"] = request.form.get("company", "")
        session["name"]    = request.form.get("name", "")
        session["email"]   = request.form.get("email", "")
        return redirect(url_for("dashboard"))
    return render_template("onboarding.html")

@app.route("/dashboard")
def dashboard():
    if not session.get("email"):
        return redirect(url_for("onboarding"))
    user = {
        "name":    session.get("name", "Utilisateur"),
        "company": session.get("company", "Mon Entreprise"),
        "email":   session.get("email", "")
    }
    mes_factures  = [f for f in factures  if f["owner"] == session["email"]]
    mes_debiteurs = [d for d in debiteurs if d["owner"] == session["email"]]
    total_due     = sum(f["amount"] for f in mes_factures if f["status"] != "paid")
    total_retard  = sum(f["amount"] for f in mes_factures if f["status"] == "overdue")
    total_paid    = sum(f["amount"] for f in mes_factures if f["status"] == "paid")
    return render_template("dashboard.html",
        user=user, factures=mes_factures, debiteurs=mes_debiteurs,
        total_due=total_due, total_retard=total_retard, total_paid=total_paid)

@app.route("/ajouter-debiteur", methods=["POST"])
def ajouter_debiteur():
    if not session.get("email"):
        return redirect(url_for("onboarding"))
    debiteurs.append({
        "id":      len(debiteurs) + 1,
        "owner":   session["email"],
        "name":    request.form.get("name", ""),
        "email":   request.form.get("email", ""),
        "company": request.form.get("company", ""),
        "phone":   request.form.get("phone", ""),
    })
    return redirect(url_for("dashboard"))

@app.route("/ajouter-facture", methods=["POST"])
def ajouter_facture():
    if not session.get("email"):
        return redirect(url_for("onboarding"))
    due_date = request.form.get("due_date", "")
    days_late, status = 0, "upcoming"
    if due_date:
        due = datetime.strptime(due_date, "%Y-%m-%d").date()
        today = date.today()
        if due < today:
            days_late = (today - due).days
            status = "overdue"
        elif (due - today).days <= 7:
            status = "pending"
    factures.append({
        "id":          len(factures) + 1,
        "owner":       session["email"],
        "debiteur_id": int(request.form.get("debiteur_id", 0)),
        "amount":      float(request.form.get("amount", 0)),
        "due_date":    due_date,
        "status":      status,
        "days_late":   days_late,
        "ref":         f"FAC-{len(factures)+1:04d}",
    })
    return redirect(url_for("dashboard"))

@app.route("/envoyer-relance/<int:facture_id>", methods=["POST"])
def envoyer_relance(facture_id):
    if not session.get("email"):
        return jsonify({"error": "Non autorisé"}), 401
    facture  = next((f for f in factures  if f["id"] == facture_id), None)
    debiteur = next((d for d in debiteurs if d["id"] == facture["debiteur_id"]), None)
    if not facture or not debiteur:
        return jsonify({"error": "Introuvable"}), 404
    try:
        email_data = generate_email_gemini(debiteur, facture, session.get("company"))
        resend.Emails.send({
            "from":    "Recouvr <onboarding@resend.dev>",
            "to":      [debiteur["email"]],
            "subject": email_data["subject"],
            "html":    email_data["body_html"]
        })
        email_log.append({
            "client":   session.get("company"),
            "debiteur": debiteur["name"],
            "email":    debiteur["email"],
            "facture":  facture["ref"],
            "montant":  facture["amount"],
            "subject":  email_data["subject"],
            "status":   "sent",
            "sent_at":  datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        return jsonify({"success": True, "message": f"Email envoyé à {debiteur['email']}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin")
def admin():
    return render_template("admin.html",
        email_log=email_log,
        total_users=len(set(f["owner"] for f in factures)) if factures else 0,
        total_factures=len(factures),
        total_debiteurs=len(debiteurs),
        total_emails=len(email_log)
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("onboarding"))

if __name__ == "__main__":
    app.run(debug=True)
