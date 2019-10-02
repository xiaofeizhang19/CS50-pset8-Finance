import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    users = db.execute("SELECT cash FROM users WHERE id = :user_id",
                    user_id = session["user_id"])
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares "
                        "FROM transactions "
                        "WHERE user_id = :user_id "
                        "GROUP BY symbol "
                        "HAVING total_shares > 0 "
                        "ORDER BY symbol ASC",
                        user_id=session["user_id"]
    )

    table_contents = []
    share_value = 0
    for row in stocks:
        symbol = row["symbol"]
        name = lookup(symbol)["name"]
        total_shares = row["total_shares"]
        price_per_share = lookup(symbol)["price"]
        total_price = price_per_share * total_shares
        table_contents.append((name, symbol, total_shares, usd(price_per_share), usd(total_price)))
        share_value += total_price

    cash_in_account = users[0]["cash"]
    balance = cash_in_account + share_value
    return render_template("index.html", table_contents=table_contents,
                           cash_in_account=usd(cash_in_account), balance=usd(balance))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        quote = lookup(symbol)
        if not symbol:
            return apology("Must provide symbol")
        if  not quote:
            return apology("Invalid symbol")

        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("Shares must be a positive integer")
        if shares <= 0:
            return apology("Shares must be a positive integer")

        rows = db.execute("SELECT * FROM users WHERE id = :user_id",
                        user_id=session["user_id"])
        available_cash = rows[0]["cash"]

        price_per_share = quote["price"]
        total_price = price_per_share * shares
        if total_price > available_cash:
            return apology("Insufficient funds")

        db.execute("INSERT INTO transactions "
                    "(user_id, symbol, price_per_share, shares, total_price, created_on) "
                    "VALUES (:user_id, :symbol, :price_per_share, :shares, :total_price, :created_on)",
                    user_id=session["user_id"],
                    symbol=symbol,
                    price_per_share=price_per_share,
                    shares=shares,
                    total_price=total_price,
                    created_on=datetime.utcnow()
        )
        db.execute("UPDATE users SET cash = cash - :total_price WHERE id = :user_id",
                    total_price=total_price,
                    user_id=session["user_id"])
        return redirect(url_for("index"))

    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args["username"]

    if len(username) == 0:
        return jsonify(False)

    rows = db.execute("SELECT * FROM users WHERE username = :username",
                      username=username)
    if rows:
        return jsonify(False)

    return jsonify(True)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    result = db.execute("SELECT symbol, shares, price_per_share, created_on FROM transactions "
                        "WHERE user_id = :user_id ORDER BY created_on DESC",
                        user_id=session["user_id"])
    history = [(row["symbol"], row["shares"], row["price_per_share"],
                row["created_on"]) for row in result]
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        quote = lookup(symbol)

        if not quote:
            return apology("Invalid symbol")

        return render_template("quoted.html", name=quote["name"],
                                symbol=quote["symbol"], price=usd(quote["price"]))

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        password_confirmation = request.form.get("confirmation")

        if not username:
            return apology("Username required", 400)
        if not password:
            return apology("Password required")
        if not password == password_confirmation:
            return apology("Passwords you entered do not match")

        rows = db.execute(
            "SELECT * FROM users WHERE username = :username",
            username=username,
        )
        if rows:
            return apology("Username already exists")

        db.execute(
            "INSERT INTO users (username, hash) VALUES (:username, :hash)",
            username=username,
            hash=generate_password_hash(password),
        )

        return redirect("/login")
    elif request.method == "GET":
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        price_per_share = quote["price"]

        result = db.execute("SELECT SUM(shares) as total_shares FROM transactions "
                            "WHERE user_id = :user_id AND symbol = :symbol",
                            user_id=session["user_id"],
                            symbol=symbol)
        shares_in_account = result[0]["total_shares"]

        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("Shares must be a positive integer")
        if shares <= 0:
            return apology("Shares must be a positive integer")
        if shares > shares_in_account:
            return apology("Can not sell more than you own")

        total_price = price_per_share * shares

        db.execute("INSERT INTO transactions (user_id, symbol, price_per_share, shares, total_price, created_on) "
                    "VALUES (:user_id, :symbol, :price_per_share, :shares, :total_price, :created_on)",
                    user_id=session["user_id"],
                    symbol=symbol,
                    price_per_share=price_per_share,
                    shares=-abs(shares),
                    total_price=total_price,
                    created_on=datetime.utcnow()
        )
        db.execute("UPDATE users SET cash = cash + :total_price WHERE id = :user_id",
                    total_price = total_price,
                    user_id=session["user_id"])
        return redirect("/")
    else:
        result = db.execute("SELECT symbol, SUM(shares) as total_shares "
                             "FROM transactions "
                             "WHERE user_id = :user_id "
                             "GROUP BY symbol "
                             "HAVING total_shares > 0",
                             user_id=session["user_id"])

        symbols = [(row["symbol"], row["total_shares"]) for row in result]

        return render_template("sell.html", symbols=symbols)


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        if not current_password:
            return apology("Please enter your current password")

        rows = db.execute("SELECT * FROM users WHERE id = :id",
                          id=session["user_id"])
        if not check_password_hash(rows[0]["hash"], current_password):
            return apology("Wrong password", 403)

        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        if new_password != confirm_password:
            return apology("Passwords do not match")

        db.execute("UPDATE users SET hash = :hash WHERE id = :user_id",
                   hash=generate_password_hash(new_password),
                   user_id=session["user_id"])
        return redirect(url_for("index"))

    elif request.method == "GET":
        return render_template("change_password.html")


@app.route("/add_funds", methods=["GET", "POST"])
@login_required
def add_funds():
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount"))
        except:
            return apology("Invalid amount")

        db.execute("UPDATE users SET cash = cash + :amount WHERE id = :user_id",
               amount=amount,
               user_id=session["user_id"])
        return redirect(url_for("index"))

    elif request.method == "GET":
        return render_template("add_funds.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
