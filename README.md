p2pool-donation-tool
====================

This repository contains the workhorse files for http://blisterpool/p2pdonate. It uses a web.py template engine to serve pages, and the pages are served based on the two classes p2pdonate and p2pdonationstatus.

The other functions are helper functions called by the above classes.

The main script (check_donations.py) connects to the bitcoin wallet, p2pool node and db to check which donations have been filled (3 confirmations), after which it fills out more db, sends payment out and an email to the donater (if one has been given), as well as an email to the administrator with any errors.
