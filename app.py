#straigforward flask applications
import json, config, time, smtplib, ssl
from flask import Flask, request, jsonify, render_template, json
from binance.client import Client
from binance.enums import *


app = Flask(__name__)
###################################################################################################################
@app.route('/')
def welcome():
    return render_template('index.html')

client = Client(config.API_KEY, config.API_SECRET, tld='us')
###################################################################################################################
@app.route('/webhook', methods=['POST'])
def webhook():
    #print(request.data)
    '''input::
    {
    "passphrase": "aaksldjfla",
    "time": "{{timenow}}",
    "ticker": "{{ticker}}",
    "confirmation": "strong buy",
    "price" = {{price}}
    }
    '''
    data = json.loads(request.data)

    if data['passphrase'] != config.WEBHOOK_PASSPHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }
    #print(data['ticker'])


    confirmation = data['confirmation'].lower()
    current_asset = data['ticker']
    
    stop_loss_trigger_percent = .94
    stop_limit_price_percent = .93

    limit_buy_percent = 1
    limit_sell_percent = 1
    if current_asset == "BTCUSD":
        pr_price = 0
        pr_amount = 5
    if current_asset == "ETHUSD":
        pr_price = 0
        pr_amount = 4
    if current_asset == "DOGEUSD":
        pr_price = 4
        pr_amount = 0

    #price_of_current_asset = float(client.get_symbol_ticker(symbol=current_asset)['price'])
    price_of_current_asset = float(data['price'])
    #print("price of asset = " + str(price_of_current_asset)+"\n")
    packet = "Currently trying to place an order " + confirmation + " of  " + current_asset
    print(packet)
    send_email(2, current_asset, price_of_current_asset,61, packet)

    #cancel all open order for this asset if there are any 
    open_orders = client.get_open_orders(symbol=current_asset)
    #print(open_orders)
    #print("open orders above")
    if len(open_orders) > 0:
        for i in open_orders:
            #print(i)
            sym_orderId = int(i['orderId'])
            #print("orderId == " + str(sym_orderId))
            cancelled = client.cancel_order(symbol = current_asset,orderId = sym_orderId)
        #send_email(2, current_asset, price_of_current_asset,69, "have cancelled orders")     
        time.sleep(1)

        print("cancelled orders")

    if confirmation == 'strong buy':
        take_profit_percent = 1.027
        print("went through strong buy\n")
        order_response  = strong_buy(price_of_current_asset,current_asset, take_profit_percent, stop_loss_trigger_percent, stop_limit_price_percent,limit_buy_percent,pr_price,pr_amount)
    if confirmation == 'buy':
        take_profit_percent = 1.02
        order_response  = reg_buy(price_of_current_asset,current_asset, take_profit_percent, stop_loss_trigger_percent, stop_limit_price_percent,limit_buy_percent,pr_price,pr_amount)
    if confirmation == 'strong sell' or confirmation == 'sell' :
        #send_email(2, current_asset, price_of_current_asset,0, "both_sell if statement")
        order_response = both_sell(current_asset, price_of_current_asset,limit_sell_percent,pr_price,pr_amount)

    '''
    quantity = data['strategy']['order_contracts']
    ticker = data['ticker']
    order_response = order(side, quantity, ticker)
    '''
    print(order_response)

    if order_response:
        return {
                "code": "success",
                "message": "order succeeded"
        }
    else:
        print("order failed")
        return {
                "code": "error",
                "message": "order failed"
        }

###################################################################################################################
def available_asset_amount(current_asset):
    '''
    # This function will return the quantity to buy of the current asset 
    :input = current_asset (str)
    :returns a dictionary with amount and price
    '''

    b_btc = float(client.get_asset_balance(asset='BTC')['free'])
    b_eth = float(client.get_asset_balance(asset='ETH')['free'])
    b_doge = float(client.get_asset_balance(asset='DOGE')['free'])
    b_usd = float(client.get_asset_balance(asset='USD')['free'])

    p_btc = float(client.get_symbol_ticker(symbol="BTCUSD")['price'])
    p_eth = float(client.get_symbol_ticker(symbol="ETHUSD")['price'])
    p_doge = float(client.get_symbol_ticker(symbol="DOGEUSD")['price'])

    if current_asset == 'BTCUSD':
        bname_asset = 'BTC'
        curr_share = .3
        asset_price = p_btc
        currently_held_dollars = b_btc * p_btc
    
    if current_asset == 'ETHUSD':
        bname_asset = 'ETH'
        curr_share = .4
        asset_price = p_eth
        currently_held_dollars = b_eth * p_eth
    
    if current_asset == 'DOGEUSD':
        bname_asset = 'DOGE'
        curr_share = .3
        asset_price = p_doge
        currently_held_dollars= b_doge * p_doge
   
    total_balance = b_btc*p_btc + b_eth*p_eth + b_doge*p_doge + b_usd
    max_available = total_balance*curr_share

    #print(max_available)
    #print(currently_held_dollars)

    room_to_buy = max_available - currently_held_dollars 

    if b_usd < room_to_buy:
        room_to_buy = b_usd

    if room_to_buy < 11:
        #dont have enough to place an order
        quantity_can_buy = 0
    else:
        quantity_can_buy = (room_to_buy - 1)/asset_price
    
    #if current_asset == 'DOGEUSD':
     #   quantity_can_buy = round(quantity_can_buy)
    currently_held_coins = currently_held_dollars/asset_price

    return {
            "amount": quantity_can_buy,
            "dollars": quantity_can_buy*asset_price,
            "price": asset_price,
            "current_held": currently_held_coins,
            "bname": bname_asset
        }
###################################################################################################################
def strong_buy(price_of_current_asset,current_asset, take_profit_percent, stop_loss_trigger_percent, stop_limit_price_percent,limit_buy_percent,pr_price,pr_amount):
    '''
    # I want to place a buy order for the given symbol and set a stop loss using OCO
    :inputs = amount(int), current_asset(str), take_profit_price(float), stop_loss_trigger(float), stop_limit_price(float)
    
    :outputs = order object
    i.e. current_asset = ETHUSD 
    '''
   
    avail_dict = available_asset_amount(current_asset)
    if avail_dict['dollars'] < 10:
        print("failed bc cant buy anymore")
        send_email(1, current_asset, 0,0, "Dont have enough money to buy more(Strong)")
        return False
    
    curr_price = price_of_current_asset
    num_coins = round(avail_dict['amount']*(.90),pr_amount)
    curr_held = avail_dict['current_held']

    limit_buy_price = round(curr_price*limit_buy_percent,pr_price)
    #place limit buy order

    #cancel all orders for this asset

    try:
        print(f"sending order {'LIMIT'} - {'buy'} {num_coins} of {current_asset}")
        order = client.order_market_buy(symbol=current_asset, quantity = num_coins)
        send_email(0, current_asset, limit_buy_price,num_coins, "Strong_Bought")
        time.sleep(3)
        #order = client.order_limit_buy(symbol=current_asset,quantity=str(num_coins),price=str(limit_buy_price))
        #print(order)
    except Exception as e:
        print("an exception occured - {}".format(e))
        send_email(1, current_asset, limit_buy_price,num_coins, "Strong_Buy")
        return False

    #Place oco order
    #price = take profit price
    #stop price, when the limit order is triggered
    #limit = at what price i would want to sell at
    #take profit after 10 percent

    tp_price = curr_price * take_profit_percent
    sl_price = curr_price *stop_loss_trigger_percent
    stop_limit_price = curr_price *stop_limit_price_percent
 
    alreadyHoldingPlusNewOrder = curr_held + num_coins
    oco_sell_part = .8
    tp_2_amount = round (alreadyHoldingPlusNewOrder * (1-oco_sell_part) *.99, pr_amount)
    alreadyHoldingPlusNewOrder = alreadyHoldingPlusNewOrder * oco_sell_part

    alreadyHoldingPlusNewOrder = round(alreadyHoldingPlusNewOrder*.99,pr_amount)
    #open_orders = client.get_open_orders(symbol=current_asset)
    bname_asset = avail_dict['bname']
  
    flag = 0
    t = 0
    #want to only place the oco order once the limit order is filled    
    while flag == 0: 
        t = t + 1
        time.sleep(3)
        ihave_rn = float(client.get_asset_balance(asset=bname_asset)['free'])
        if (float(ihave_rn)) >= alreadyHoldingPlusNewOrder:
            try:
                client.order_oco_sell(
                symbol= current_asset,                                            
                quantity= alreadyHoldingPlusNewOrder,                                            
                price= str(round(tp_price,pr_price)),                                            
                stopPrice= str(round(sl_price,pr_price)),                                            
                stopLimitPrice= str(round(stop_limit_price,pr_price)),                                            
                stopLimitTimeInForce= 'FOK')
                time.sleep(2)
                send_email(0, current_asset, tp_price,alreadyHoldingPlusNewOrder, "OCO_Sold (Strong) ")
                tp2_price = tp_price * 1.02
                client.order_limit_sell(symbol=current_asset,quantity=tp_2_amount,price=str(round(tp2_price,pr_price)))
                break;
            except Exception as e:
                print("an exception occured - {}".format(e))
                send_email(1, current_asset, tp_price,alreadyHoldingPlusNewOrder, "OCO_Sell (Strong) ")
                return False
        if t == 6:
            send_email(1, current_asset, tp_price,alreadyHoldingPlusNewOrder, "OCO_Sell_too long (Strong) ")
            return order
            

    return order
 ###################################################################################################################   
def reg_buy(price_of_current_asset,current_asset, take_profit_percent, stop_loss_trigger_percent, stop_limit_price_percent,limit_buy_percent,pr_price,pr_amount):
    '''
    # I want to place a buy order for the given symbol and set a stop loss using OCO
    :inputs = amount(int), current_asset(str), take_profit_price(float), stop_loss_trigger(float), stop_limit_price(float)
    
    :outputs = order object
    i.e. current_asset = ETHUSD 
    '''
    avail_dict = available_asset_amount(current_asset)
    if avail_dict['amount'] == 0:
        print("failed bc cant buy anymore")
        send_email(1, current_asset, 0,0, "Dont have enough money to buy more (Reg")
        return False

    curr_price = price_of_current_asset
    num_coins = round(avail_dict['amount']*(.70),pr_amount)
    curr_held = avail_dict['current_held']

    limit_buy_price = round(curr_price*limit_buy_percent,pr_price)
    #place limit buy order
 
    try:
        print(f"sending order {'LIMIT'} - {'buy'} {num_coins} of {current_asset}")
        order = client.order_market_buy(symbol=current_asset, quantity = num_coins)
        #order = client.order_limit_buy(symbol=current_asset,quantity=str(num_coins),price=str(limit_buy_price))
        send_email(0, current_asset, limit_buy_price,num_coins, "Reg_Buy")
        time.sleep(3)
        #print(order)
    except Exception as e:
        print("an exception occured - {}".format(e))
        send_email(1, current_asset, limit_buy_price,num_coins, "Reg_Buy")
        return False
    
    
    #Place oco order
    #price = take profit price
    #stop price, when the limit order is triggered
    #limit = at what price i would want to sell at
    #take profit after 10 percent

    tp_price = curr_price *take_profit_percent
    sl_price = curr_price *stop_loss_trigger_percent
    stop_limit_price = curr_price *stop_limit_price_percent
 
    alreadyHoldingPlusNewOrder = curr_held + num_coins
    alreadyHoldingPlusNewOrder = round(alreadyHoldingPlusNewOrder*.98,pr_amount)
  
    #open_orders = client.get_open_orders(symbol=current_asset)
    bname_asset = avail_dict['bname']
    
    flag = 0
    t = 0
    #want to only place the oco order once the limit order is filled    
    while flag == 0: 
        t = t + 1
        time.sleep(3)
        ihave_rn = float(client.get_asset_balance(asset=bname_asset)['free'])
        if (float(ihave_rn)) >= alreadyHoldingPlusNewOrder:
            try:
                client.order_oco_sell(
                symbol= current_asset,                                            
                quantity= alreadyHoldingPlusNewOrder,                                            
                price= str(round(tp_price,pr_price)),                                            
                stopPrice= str(round(sl_price,pr_price)),                                            
                stopLimitPrice= str(round(stop_limit_price,pr_price)),                                            
                stopLimitTimeInForce= 'FOK')
                send_email(0, current_asset, tp_price,alreadyHoldingPlusNewOrder, "OCO_Sold (Reg) ")
                break;
            except Exception as e:
                print("an exception occured - {}".format(e))
                send_email(1, current_asset, tp_price,alreadyHoldingPlusNewOrder, "OCO_Sell (Reg) ")
                return False
        if t == 6:
            send_email(1, current_asset, tp_price,alreadyHoldingPlusNewOrder, "OCO_Sell_too long (Reg) ")
            return order   

    return order
###################################################################################################################

def both_sell(current_asset,curr_price,limit_sell_percent,pr_price,pr_amount):
    '''
    # I want to place a buy order for the given symbol and set a stop loss using OCO
    :inputs = amount(int), current_asset(str), take_profit_price(float), stop_loss_trigger(float), stop_limit_price(float)
    
    :outputs = order object
    '''
    #current_asset == DOGEUSD

    if current_asset == 'BTCUSD':
        coin_name = 'BTC'
    
    if current_asset == 'ETHUSD':
        coin_name = 'ETH'
    
    if current_asset == 'DOGEUSD':
        coin_name = 'DOGE'
    # make sure you own some of what you are selling right now

    asset_balance = float(client.get_asset_balance(asset=coin_name)['free'])*.99
    #asset_locked = float(client.get_asset_balance(asset=coin_name)['locked'])
    asset_balance = round(asset_balance,pr_amount)
    #print("asset_balance = " + str(asset_balance))
    #print("asset_locked = " + str(asset_locked))

    if asset_balance*curr_price < 10:
        print("cant sell what i dont have \n")
        send_email(1, current_asset, 0,asset_balance, "Dont have enough assets to sell")
        return False

    limit_sell_price = round(curr_price*limit_sell_percent,pr_price)
    #place limit buy order
    #print("limit_sell_price: "+str(limit_sell_price))
    #print("asset_balance: "+str(asset_balance))
    #return False

    try:
        print(f"sending order {'LIMIT'} - {'sell'} {asset_balance} of {current_asset}")
        order = client.order_market_sell(symbol=current_asset, quantity=asset_balance)
        #order = client.order_limit_sell(symbol=current_asset,quantity=str(asset_balance),price=str(limit_sell_price))
        #print(order)
    except Exception as e:
        print("an exception occured - {}".format(e))
        send_email(1, current_asset, limit_sell_price,asset_balance, "Sell")
        return False
    send_email(0, current_asset, limit_sell_price,asset_balance, "Sell")
    return order
###################################################################################################################
def send_email(error, ticker, price,quantity, action):
    port = 465  # For SSL
    smtp_server = "smtp.gmail.com"
    sender_email = "email@gmail.com"  # Enter your address
    receiver_email = "email@gmail.com"  # Enter receiver address
    password = config.EMAIL_PASSWORD
    context = ssl.create_default_context()
    
    if error == 1:
        subject = "There was an error" 
        body = "Was trying to " + action + " " +str(quantity) + " " + ticker +  " @" + str(price)
    
    if error == 0: 
        subject = action + " " +str(quantity) + " " + ticker +  " @" + str(price) 
        body = "Order Successful"

    if error == 2:
        subject = action  + " " + str(quantity) + " " + ticker +  " @ " + str(price) 
        body = "Processing"
    

    message ="Subject: {}\n\n {}".format(subject, body) 
    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message)