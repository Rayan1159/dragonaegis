from flask import Flask

app = Flask(__name__)
app.logger.disabled = True

def run():
    app.run('localhost', 8080)

@app.route("/")
def index():
    return "<p>server enabled</p>"