from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "recouvr-secret-key-2024"

@app.route("/", methods=["GET", "POST"])
def onboarding():
    if request.method == "POST":
        # Récupère les infos du formulaire
        session["company"] = request.form.get("company")
        session["name"]    = request.form.get("name")
        session["email"]   = request.form.get("email")
        return redirect(url_for("dashboard"))
    
    # Si déjà inscrit, va direct au dashboard
    if session.get("email"):
        return redirect(url_for("dashboard"))
    
    return render_template("onboarding.html")

@app.route("/dashboard")
def dashboard():
    if not session.get("email"):
        return redirect(url_for("onboarding"))
    return render_template("onboarding.html", user=session)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("onboarding"))

if __name__ == "__main__":
    app.run(debug=True)
