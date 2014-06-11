#!/usr/bin/env python
# check_donations.py
# runs once per minute, looking for unpaid donations that now have 3 confirmations, then acting on it.

import json, urllib2, sys, web, smtplib, datetime, logging, traceback
from bitcoinrpc.authproxy import AuthServiceProxy
from decimal import *
db = web.database(dbn='postgres', db='dbname', user='username', pw='userpw')
# read config file
file_location = "<path to config file>"
with open(file_location, 'r') as f:
        config = json.load(f)

coins = {}
for coin, settings in config.iteritems():
        coins[coin] = {'access': AuthServiceProxy("http://%s:%s@%s:%s/" % (settings['rpcuser'], settings['rpcpass'], settings['rpcserver'], settings['rpcport']))}
        coins[coin]['balance'] = coins[coin]['access'].getbalance()

rpc = coins['bitcoin']['access']
# bitcoin wallet can now be accessed via rpc.command()

def check_transactions():
        # check db for unpaid transactions
        q = db.query("select * from donations where status = $status", vars={'status':"unpaid"})
        if len(q) > 0:
                for row in q:
                        balance = rpc.getreceivedbyaddress(row.btc_addr, 3)
                        if float(balance) == row.amount or float(balance) > row.amount:
                                try:
                                        message = ""
                                        url = "http://127.0.0.1:9332/patron_sendmany/"+str(row.amount)+"/"+str(row.cutoff)
                                        p2pool_payout_addresses = json.load(urllib2.urlopen(url))
                                        t = db.transaction()
                                        # create payment url
                                        url = "http://blisterpool.com/p2pdonationstatus/%s" % row.special_id
                                        total = 0.0
                                        tip = 0.0
                                        defaults = {'url':url, 'refund':row.return_addr, 'amount':row.amount, 'cutoff':row.cutoff, 'email':row.email, 'special_id':row.special_id, 'donation_addr':row.btc_addr, 'balance':balance, 'total':total, 'tip':float(tip)}
                                        # create dynamic payouts table based on this special id
                                        try:
                                                db.query("create table payouts_"+str(row.special_id)+" () inherits (payouts)")
                                        except:
                                                t.rollback()
                                                raise
                                        for address, amount in p2pool_payout_addresses.iteritems():
					# tally the total being sent to miners to store in db
                                                total += amount
                                                try:
						# put the miner payments into db
                                                        db.query("insert into payouts_"+str(row.special_id)+" (btc_addr, amount) values ($address, $amount)", vars={'address':address, 'amount':amount})
                                                except:
                                                        t.rollback()
                                                        raise

                                        # apply tip to the sendmany if it's greater than zero
				  # balance shows total received to the bitcoin address, and total equals the sum of p2pool_payout_address amounts, as well as row.amount
                                        defaults['tip'] = Decimal(balance - Decimal(total))
                                        if defaults['tip'] > 0.0:
                                                p2pool_payout_addresses[rpc.getnewaddress('tips')] = defaults['tip']
                                        defaults['total'] = total
                                        # update donations database set status to paid
                                        try:
                                                db.query("update donations set status=$status, total_paid=$total, tip=$tip  where special_id = $id", vars={'status':"paid", 'id':row.special_id, 'total':total, 'tip':float(tip)})
                                        except:
                                               t.rollback()
                                                raise
                                        t.commit()
                                        # unlock wallet for 15 seconds
                                        try:
                                                rpc.walletpassphrase('walletpassphrase', 15)
					# send via sendmany all the values in p2pool_payout_addresses, and store txid in db.
                                                txid = rpc.sendmany("donations", p2pool_payout_addresses) 
                                                db.query("update payouts_"+str(row.special_id)+" set txid = $txid", vars={'txid':txid})
                                                db.query("update donations set txid=$txid where special_id=$id", vars={'txid':txid, 'id':row.special_id})
                                        except:
                                                raise
                                        # send out confirmation email
                                        if defaults['email'] != "None":
                                                SendConfirmationEmail(defaults)
                                except:
                                        message += traceback.format_exc()
			    # send admininstrator email for confirmations and errors
                                defaults['email'] = "p2pool@blisteringdevelopers.com"
                                SendConfirmationEmail(defaults, message)


def SendConfirmationEmail(details, note=""):
        import smtplib
        from email.mime.text import MIMEText
        from email.MIMEMultipart import MIMEMultipart
        message = ""
        message += note + "\n\n"
        message += "Blisterpool Donation Service\n\n"
        message += "A donation has been paid! Here are the details:\n\n"
        message += "Donation Amount:\t%.8f btc\n" % details['amount']
        message += "Cutoff Amount:\t\t%.8f btc\n" % details['cutoff']
        if details['tip'] == 0.0:
                message += "Tip:\t\t\t%.8f btc (if you wish to send a tip, you can still send it to the donation address below)\n" % details['tip']
        else:
                message += "Tip:\t\t\t%.8f btc\n" % details['tip']

        message += "\nDonation Address:\t%s\n" % details['donation_addr']
        expected = details['amount'] + float(details['tip'])
        message += "Total Expected:\t\t%.8f btc\n" % expected
        message += "Total Received:\t\t%.8f btc\n" % float(details['balance'])
        message += "Total sent to P2Pool Miners:\t %.8f btc\n" % float(details['total'])
        message += "\nYou can view the donation status here: %s\n\n" % details['url']

        fromaddr = "p2pool@blisteringdevelopers.com"
        msg = MIMEMultipart()
        msg['From'] = fromaddr
        toaddr = str(details['email'])
        msg['To'] = toaddr
        msg['Subject'] = "Blisterpool Donation Paid!"
        body = message
        msg.attach(MIMEText(body, 'plain'))
        try:
                server = smtplib.SMTP('mailserver', 25)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login("email login", "email password")
                text = msg.as_string()
                server.sendmail(fromaddr, toaddr, text)
        except:
                raise
if __name__ == "__main__":
        check_transactions()
