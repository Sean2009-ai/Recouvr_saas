# Recouvr SaaS - v2.2
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, date
import resend
import os

app = Flask(__name__)
app.secret_key = "recouvr-secret-2024"
resend.api_key = "re_JCPxxYWh_2J4bmCdfa5VoLp6kQ5SkVeA5"

debiteurs = []
factures  = []
email_log = []

def generate_email(debiteur, facture, company):
    if facture["days_late"] >= 15:
        tone = "mise en demeure"
        intro = f"Malgré nos relances précédentes, nous constatons que la facture {facture['ref']} d'un montant de <strong>{facture['amount']:,.0f} FCFA</strong> reste impayée depuis <strong>{facture['days_late']} jours</strong>."
        cta = "Sans règlement sous 48h, nous serons contraints d'engager des procédures de recouvrement."
    elif facture["days_late"] >= 7:
        tone = "relance ferme"
        intro = f"Nous vous rappelons que la facture {facture['ref']} d'un montant de <strong>{facture['amount']:,.0f} FCFA</strong> est en retard de <strong>{facture['days_late']} jours</strong>."
        cta = "Merci de procéder au règlement dans les meilleurs délais."
    else:
        tone = "rappel courtois"
        intro = f"Nous vous rappelons que la facture {facture['ref']} d'un montant de <strong>{facture['amount']:,.0f} FCFA</strong> arrive à échéance."
        cta = "Merci de bien vouloir procéder au règlement à votre convenance."

    subject = f"[{company}] Relance facture {facture['ref']} — {facture['amount']:,.0f} FCFA"
    body_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#fff;">
      <div style="background:linear-gradient(135deg,#C9963A,#E09030);padding:20px 24px;border-radius:10px 10px 0 0;">
        <h1 style="color:#000;margin:0;font-size:22px;">Recouvr</h1>
        <p style="color:#000;margin:4px 0 0;font-size:12px;opacity:0.7;">Recouvrement B2B · {company}</p>
      </div>
      <div style="background:#f9f9f9;padding:28px 24px;border-radius:0 0 10px 10px;border:1px solid #eee;">
        <p style="color:#333;font-size:15px;">Bonjour <strong>{debiteur['name']}</strong>,</p>
        <p style="color:#555;font-size:14px;line-height:1.7;margin-top:16px;">{intro}</p>
        <div style="background:#fff;border:1px solid #ddd;border-radius:8px;padding:16px;margin:20px 0;">
          <p style="margin:0;color:#888;font-size:12px;">Référence facture</p>
          <p style="margin:4px 0 0;color:#000;font-size:16px;font-weight:bold;">{facture['ref']}</p>
          <p style="margin:12px 0 0;color:#888;font-size:12px;">Montant dû</p>
          <p style="margin:4px 0 0;color:#C9963A;font-size:22px;font-weight:900;">{facture['amount']:,.0f} FCFA</p>
          <p style="margin:12px 0 0;color:#888;font-size:12px;">Échéance</p>
          <p style="margin:4px 0 0;color:#E0504A;font-size:14px;font-weight:bold;">{facture['due_date']}</p>
        </div>
        <p style="color:#555;font-size:14px;line-height:1.7;">{cta}</p>
        <div style="text-align:center;margin:24px 0;">
          <a href="https://recouvr-saas.onrender.com/payer/{facture['ref']}" 
             style="background:linear-gradient(135deg,#C9963A,#E09030);color:#000;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:800;font-size:15px;">
            Payer maintenant →
          </a>
        </div>
        <p style="color:#aaa;font-size:12px;margin-top:24px;border-top:1px solid #eee;padding-top:16px;">
          Pour toute question, contactez-nous · {company}<br>
          Propulsé par <strong>Recouvr</strong>
        </p>
      </div>
    </div>"""
    return subject, body_html

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
    if not facture:
        return jsonify({"error": "Facture introuvable"}), 404
    debiteur = next((d for d in debiteurs if d["id"] == facture["debiteur_id"]), None)
    if not debiteur:
        return jsonify({"error": "Débiteur introuvable"}), 404
    try:
        subject, body_html = generate_email(debiteur, facture, session.get("company", ""))
        resend.Emails.send({
            "from":    "Recouvr <onboarding@resend.dev>",
            "to":      [debiteur["email"]],
            "subject": subject,
            "html":    body_html
        })
        email_log.append({
            "client":   session.get("company"),
            "debiteur": debiteur["name"],
            "email":    debiteur["email"],
            "facture":  facture["ref"],
            "montant":  facture["amount"],
            "subject":  subject,
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
