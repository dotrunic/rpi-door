from flask import Flask, render_template, jsonify
from logging import log, stash

app = Flask(__name__)

@app.route("/")

log("hello logging from server")

def home():
    return render_template("index.html")

@app.route("/logs")
def getLogs():
    return jsonify(stash)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
