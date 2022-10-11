import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
uri = os.getenv("DATABASE_URL")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://")
db = SQL(uri)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    # retrieve the balance and the record for all transaction of the session user
    balance_share = db.execute(
        "SELECT DISTINCT ON (username_id), symbol, share_name, SUM (quantity) as sum_quantity, price_share, quantity, quantity*price_share AS total_sum FROM transactions WHERE username_id = ? GROUP BY symbol", session.get("user_id"))
    total_sum = 0
    for row in balance_share:
        newprice = (lookup(row["symbol"]))["price"]
        row["sum_quantity"] = int(row["sum_quantity"])
        row["total_sum"] = row["sum_quantity"] * newprice
        # calculate the total sum including share prices and cash balance
        total_sum += row["total_sum"]
        row["price_share_usd"] = usd(newprice)
        row["total_sum_usd"] = usd(row["total_sum"])
    # retrieve the cash balance of the user and calculate the total assets the user has
    balance_cash = db.execute("SELECT DISTINCT ON (cash) FROM users WHERE id = ?", session.get("user_id"))
    balance_cash = balance_cash[0]["cash"]
    total_sum = balance_cash + total_sum
    return render_template("index.html", balance_cash=usd(balance_cash), balance_share=balance_share, total=usd(total_sum))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        # import the values from the form
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # check up the price of the selected symbol
        quote = lookup(symbol)

        # check if the input is correct
        if quote == None:
            return apology("must provide a valid symbol")
        elif not shares:
            return apology("must provide a share amount")
        # validate if input of shares is indeed an integer
        try:
            check = int(shares)
        except ValueError:
            return apology("must provide a valid integer share amount")
        if check < 0:
            return apology("must provide a valid positive share amount")
        # retrieve the balance account of the user and calculate the price of the transaction
        balance = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))
        balance = balance[0]["cash"]
        price = float(quote["price"]) * int(shares)

        # validation of sufficient funds
        if balance < price:
            return apology("no sufficient funds")

        # update balance in the database and redirect
        balance -= price
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, session.get("user_id"))
        db.execute("INSERT INTO transactions (username_id, price_transaction, price_share, quantity, symbol, transaction_type, share_name) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   session.get("user_id"), price, int(quote["price"]), int(shares), symbol, "buy", quote["name"])
        return redirect("/")
    else:
        # print balance when visiting the buy section
        balance = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))
        balance = balance[0]["cash"]
        balance = usd(balance)
        return render_template("buy.html", balance=balance)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    if request.method == "GET":
        # query the database for history
        transactions = db.execute("SELECT * FROM transactions WHERE username_id")
        for row in transactions:
            # convert format of prices to USD
            row["price_share"] = usd(row["price_share"])
            row["price_transaction"] = usd(row["price_transaction"])
        return render_template("history.html", transactions=transactions)
    else:
        return apology("error showing")


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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

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
    if request.method == "POST":
        # pull new share prices from the lookup function
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        # make sure the input in not empty or invalid
        if quote == None:
            return apology("must provide a symbol")
        # convert format to USD and then render answer
        quote["price"] = usd(quote["price"])
        return render_template("quoted.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # save input from user
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        # validate if any input is empty
        if not username or not password or not confirmation:
            return apology("No fields can be cannot be empty")
        # validate if the user does not exist in the first place
        exists = db.execute("SELECT id FROM users WHERE username = ?", username)
        if exists:
            return apology("the username already exists")
        print(exists)
        # create hash from password and save it to user table
        hash = generate_password_hash(password)
        if password == confirmation:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)
            return redirect("/")
        else:
            return apology("Passwords should be identical")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # check if user has enough shares to sell
        symbol = request.form.get("symbol")
        share_quantity = request.form.get("shares")
        if not share_quantity and not symbol:
            return apology("Provide the number of share to sell")
        try:
            share_quantity = int(share_quantity)
        except ValueError:
            return apology("must provide a valid integer share amount")
        if share_quantity < 0:
            return apology("must provide a valid positive share mount")
        # query database for user transaction summary
        balance_share = db.execute("SELECT username_id, symbol, share_name, SUM (quantity), price_share, quantity, quantity*price_share AS total_sum FROM transactions WHERE username_id = ? AND symbol = ? GROUP BY symbol", session.get("user_id"), symbol)
        balance_share = balance_share[0]
        # check if user has enough shares to sell and sell them
        if share_quantity <= int(balance_share["quantity"]):
            # calculate the price of transaction
            quote = lookup(symbol)
            price_transaction = share_quantity * quote["price"]
            # add transaction to transactions table
            db.execute("INSERT INTO transactions (username_id, price_transaction, price_share, quantity, symbol, transaction_type, share_name) VALUES(?, ?, ?, ?, ?, ?, ?)", session.get("user_id"), -price_transaction, int(quote["price"]), -int(share_quantity), symbol, "sell", quote["name"])
            # update to cash column in the users table
            cash = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))
            cash = cash[0]
            cash["cash"] += price_transaction
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash["cash"], session.get("user_id"))
        else:
            # print apology if no sufficient funds
            return apology("No suffucient shares")

        return redirect("/")

    else:
        # query the database to check if any
        balance_share = db.execute(
            "SELECT username_id, symbol, share_name, SUM (quantity), price_share, quantity, quantity*price_share AS total_sum FROM transactions WHERE username_id = ? GROUP BY symbol", session.get("user_id"))
        return render_template("sell.html", balance_share=balance_share)

    return apology("TODO")