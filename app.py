# Recouvr SaaS - v2.0
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, date
import resend
import anthropic
import json
import os

app = Flask(__name__)
app.secret_key = "recouvr-secret-2024"

# Clés API
resend.api_key = "re_JCPxxYWh_2J4bmCdfa5VoLp6kQ5SkVeA5"
anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

# Base de données en mémoire (à remplacer par une vraie DB plus tard)
debiteurs = []
factures  = []
email_log = []

# ── INSCRIPTION ──────────────────────────────────
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

# ── DASHBOARD CLIENT ─────────────────────────────
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
    
    # Calcul KPIs
    total_due    = sum(f["amount"] for f in mes_factures if f["status"] != "paid")
    total_retard = sum(f["amount"] for f in mes_factures if f["status"] == "overdue")
    total_paid   = sum(f["amount"] for f in mes_factures if f["status"] == "paid")
    
    return render_template("dashboard.html",
        user=user,
        factures=mes_factures,
        debiteurs=mes_debiteurs,
        total_due=total_due,
        total_retard=total_retard,
        total_paid=total_paid
    )

# ── AJOUTER DÉBITEUR ─────────────────────────────
@app.route("/ajouter-debiteur", methods=["POST"])
def ajouter_debiteur():
    if not session.get("email"):
        return redirect(url_for("onboarding"))
    debiteur = {
        "id":      len(debiteurs) + 1,
        "owner":   session["email"],
        "name":    request.form.get("name", ""),
        "email":   request.form.get("email", ""),
        "company": request.form.get("company", ""),
        "phone":   request.form.get("phone", ""),
    }
    debiteurs.append(debiteur)
    return redirect(url_for("dashboard"))

# ── AJOUTER FACTURE ──────────────────────────────
@app.route("/ajouter-facture", methods=["POST"])
def ajouter_facture():
    if not session.get("email"):
        return redirect(url_for("onboarding"))
    due_date = request.form.get("due_date", "")
    days_late = 0
    status = "upcoming"
    if due_date:
        due = datetime.strptime(due_date, "%Y-%m-%d").date()
        today = date.today()
        if due < today:
            days_late = (today - due).days
            status = "overdue"
        elif (due - today).days <= 7:
            status = "pending"
    
    facture = {
        "id":          len(factures) + 1,
        "owner":       session["email"],
        "debiteur_id": int(request.form.get("debiteur_id", 0)),
        "amount":      float(request.form.get("amount", 0)),
        "due_date":    due_date,
        "status":      status,
        "days_late":   days_late,
        "ref":         f"FAC-{len(factures)+1:04d}",
    }
    factures.append(facture)
    return redirect(url_for("dashboard"))

# ── ENVOYER EMAIL IA ─────────────────────────────
@app.route("/envoyer-relance/<int:facture_id>", methods=["POST"])
def envoyer_relance(facture_id):
    if not session.get("email"):
        return jsonify({"error": "Non autorisé"}), 401

    facture  = next((f for f in factures  if f["id"] == facture_id), None)
    debiteur = next((d for d in debiteurs if d["id"] == facture["debiteur_id"]), None)

    if not facture or not debiteur:
        return jsonify({"error": "Facture ou débiteur introuvable"}), 404

    # Générer email avec Claude
    try:
        prompt = f"""Tu es un expert en recouvrement B2B en Afrique de l'Ouest.
Génère un email de relance professionnel.

Client créancier : {session.get('company')}
Débiteur : {debiteur['name']} ({debiteur['company']})
Montant dû : {facture['amount']:,.0f} FCFA
Référence facture : {facture['ref']}
Jours de retard : {facture['days_late']}
Lien paiement : https://recouvr-saas.onrender.com/payer/{facture['ref']}

Réponds UNIQUEMENT en JSON sans backticks :
{{
  "subject": "objet de l'email",
  "body_html": "corps HTML complet de l'email avec balises p, strong, br"
}}"""

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text
        email_data = json.loads(raw.replace("```json","").replace("```","").strip())

        # Envoyer avec Resend
        resend.Emails.send({
            "from":    "Recouvr <onboarding@resend.dev>",
            "to":      [debiteur["email"]],
            "subject": email_data["subject"],
            "html":    email_data["body_html"]
        })

        # Logger
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

# ── DASHBOARD ADMIN ──────────────────────────────
@app.route("/admin")
def admin():
    return render_template("admin.html",
        email_log=email_log,
        total_users=len(set(f["owner"] for f in factures)),
        total_factures=len(factures),
        total_debiteurs=len(debiteurs),
        total_emails=len(email_log)
    )

# ── DÉCONNEXION ──────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("onboarding"))

if __name__ == "__main__":
    app.run(debug=True)
    
