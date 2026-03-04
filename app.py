from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот для расчёта авто из Японии работает!"