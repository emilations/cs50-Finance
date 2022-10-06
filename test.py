whatever = input("Pick an integer > ")
try:
    whatever_as_an_integer = float(whatever)
    print("That was an integer.")

except ValueError:
    print("That is not an integer.")