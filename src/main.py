
'''
authenticator: screen asks user for username and password
- if username is found and password matches, then given access
- if username not found, say "username not found. please try again"
- if username found but password incorrect, say "password incorrect. please try again"
- if wrong password 3 straight times, lock user out of the cabinet for x minutes/seconds before another attempt is
  allowed
if user uses card login:
- authenticator attains the username from the card scan
    - if valid username for the cabinet, allow access
    - if not, block access, or go straight to manual login method
'''

'''
once logged in: go to screen that allows user to choose medication
- user specifies medication and amount
    - if medication not found in cabinet, say "medication not found in cabinet"
    - if found but not enough, say "can't do this much medication" and give them what is left and send flag to
      monitoring system to restock
    - if found and enough,
        - dispense medication to user
        - send dispensing note to logger with time, user, medication, amount taken, and amount left
        - update amount of that medication left (ie. if 50 of 200 taken out, new stock amount = 200-50 = 150)
'''


print("3K04 Deliverable 2")

