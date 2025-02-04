import os
import sys
import inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.append(parentdir)
sys.path.append(parentdir + '/modeling')
from os.path import join as oj
import sklearn
import copy
import numpy as np
import scipy as sp
import pandas as pd
from functions import merge_data
from sklearn.model_selection import RandomizedSearchCV
import load_data
import exponential_modeling
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor
from fit_and_predict import add_preds
from datetime import datetime, timedelta
import pygsheets

    
if __name__ == '__main__':
    NUM_DAYS_LIST = [1, 2, 3, 4, 5, 6, 7]
    df_county = load_data.load_county_level(data_dir=oj(parentdir, 'data'))
    df_county = add_preds(df_county, NUM_DAYS_LIST=NUM_DAYS_LIST, cached_dir=oj(parentdir, 'data')) # adds keys like "Predicted Deaths 1-day"    

    
    # county-level stuff (#ICU_beds is county-level)
    k_surge = 'Severity (Surge) Prediction'
    df_county[k_surge] = 2 * df_county['Predicted Deaths 3-day'] - df_county['#ICU_beds'].fillna(0)

    # rewrite pred cols
    today = datetime.today().strftime("%B %d")
    days = ['Predicted Deaths by ' + (datetime.today() + timedelta(days=i)).strftime("%B %d")
            for i in NUM_DAYS_LIST]
    remap = {
        f'Predicted Deaths {i}-day': 
        'Predicted Deaths by ' + (datetime.today() + timedelta(days=i)).strftime("%B %d")
        for i in NUM_DAYS_LIST
    }
    df_county = df_county.rename(columns=remap).sort_values(by=k_surge, ascending=False).round(decimals=1)
        
    # write to gsheets
    service_file=oj(parentdir, 'creds.json')
    FNAME = 'County-level Predictions'
    gc = pygsheets.authorize(service_file=service_file)
    sh = gc.open(FNAME)
    
    # make new ws if it doesn't exist
    '''
    titles = [wks.title for wks in sh.worksheets()]
    if not today in titles:
        sh.add_worksheet(today, index=0)
    wks = sh.worksheet_by_title(today)
    '''
    wks = sh[0]
    
    # write to ws
    ks = ['countyFIPS', 'CountyName', 'StateName'] + days + [k_surge]
    wks.update_value('A1', f"Note: this sheet is read-only (automatically generated by the data and model) - Last updated {today}")
    wks.set_dataframe(df_county[ks], (3, 1)) #update the first sheet with df, starting at cell B2. 
    print('succesfully updated county preds!')