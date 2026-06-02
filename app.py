cat > /home/claude/recouvr-flask/app.py << 'EOF'
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "recouvr-secret-2024"

# ── INSCRIPTION ──────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def onboarding():
    if session.get("email"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        session["company"] = request.form.get("company")
        session["name"]    = request.form.get("name")
        session["email"]   = request.form.get("email")
        return redirect(url_for("dashboard"))
    return render_template("onboarding.html")

# ── DASHBOARD CLIENT ─────────────────────────────
@app.route("/dashboard")
def dashboard():
    if not session.get("email"):
        return redirect(url_for("onboarding"))
    return render_template("dashboard.html", user=session)

# ── DASHBOARD ADMIN ──────────────────────────────
@app.route("/admin")
def admin():
    return render_template("admin.html")

# ── DÉCONNEXION ──────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("onboarding"))

if __name__ == "__main__":
    app.run(debug=True)
EOF
