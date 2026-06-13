from flask import Flask, render_template, jsonify
from utils import log, read_logs, reset_logs

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/logs")
def getLogs():
    return jsonify(read_logs())

if __name__ == "__main__":
    reset_logs()  # fresh log on each boot/restart
    log("[SERVER]: starting ...")
    # use_reloader=False so the startup line is not logged twice by the
    # debug reloader spawning a second process.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
