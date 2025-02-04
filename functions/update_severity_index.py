import numpy as np
import pandas as pd
from os.path import join as oj
import os
import pygsheets
import pandas as pd
import sys
import inspect
import datetime
import requests

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.append(parentdir)
sys.path.append(parentdir + '/modeling')
import load_data
from fit_and_predict import add_preds
from functions import merge_data
from viz import  viz_interactive

meanings = {
        1: 'Low',
        2: 'Moderate',
        3: 'Substantial',
        4: 'Severe',
        5: 'Critical'
    }

def add_severity_index(df, NUM_DAYS_LIST=[1, 2, 3]):
    def apply_manual_thresholds(vals, manual_thresholds = {3: 6,
                                                           2: 2,
                                                           1: 0}):
        new_col = vals * 0
        for key in sorted(manual_thresholds.keys()):
            new_col[vals >= manual_thresholds[key]] = key
        return new_col.astype(int)
    
    def percentiles_with_manual_low(vals, LOW_THRESH=1):
        '''Everything below LOW_THRESH gets severity 1
        All other things are split evenly by percentile
        '''
        new_col = vals * 0
        new_col[vals < LOW_THRESH] = 1
        new_col[vals >= LOW_THRESH] = pd.qcut(vals[vals >= LOW_THRESH], 2, labels=False) + 2
        return new_col.astype(int)
    
    
    # county-level stuff (#ICU_beds is county-level)
    df['Surge County 3-day'] = (2 * df['Predicted Deaths 3-day'] - df['#ICU_beds']) / df['#ICU_beds']
    

    # loop over num day    
    df['Total Deaths Hospital'] = (df['tot_deaths'] * df['Frac Hospital Employees of County']).fillna(0)
    for num_days in NUM_DAYS_LIST:
        df[f'Predicted New Deaths {num_days}-day'] = df[f'Predicted Deaths {num_days}-day'] - df['tot_deaths']
        
        # hospital-level deaths
        df[f'Predicted Deaths Hospital {num_days}-day'] = ((df[f'Predicted Deaths {num_days}-day']) * df['Frac Hospital Employees of County']).fillna(0)
        df[f'Predicted New Deaths Hospital {num_days}-day'] = (df[f'Predicted New Deaths {num_days}-day'] * df['Frac Hospital Employees of County']).fillna(0)
        
        # severity
        df[f'Severity {num_days}-day'] = percentiles_with_manual_low(df[f'Predicted Deaths Hospital {num_days}-day']) 
        df[f'Severity Emerging {num_days}-day'] = percentiles_with_manual_low(df[f'Predicted New Deaths Hospital {num_days}-day']) 
        
        # surge
        df[f'Surge {num_days}-day'] = (2 * df[f'Predicted Deaths Hospital {num_days}-day'] - df['ICU Beds'])
        
        
    s_hosp = f'Predicted Deaths Hospital 3-day'
    return df.sort_values(s_hosp, ascending=False).round(2)

def write_to_gsheets_and_api(df, ks_output=['Severity 1-day', 'Severity 2-day', 'Severity 3-day', 'Severity 4-day',
                                    'Severity 5-day', 'Severity 6-day', 'Severity 7-day', 'Total Deaths Hospital',
                                    'Hospital Name', 'CMS Certification Number', 'countyFIPS',
                                    'CountyName', 'StateName', 'System Affiliation', 'Latitude', 'Longitude'],
                     sheet_name='COVID Severity Index',
                     service_file='../creds.json',
                     api_file='../ian_key.env',
                     csv='_hidden_preds.csv'):
    
    d = df[ks_output]
    
    # wrote to gsheets
    print('writing to gsheets...')
    gc = pygsheets.authorize(service_file=service_file)
    sh = gc.open(sheet_name) # name of the hospital
    wks = sh[0] #select a sheet
    wks.update_value('A1', "Note: this sheet is read-only (automatically generated by the data and model)")
    wks.set_dataframe(d, (3, 1)) #update the first sheet with df, starting at cell B2. 
    
     # write to ian's api
    print('writing to api')
    with open(api_file, 'r') as f:
        auth_token = f.read()
    hed = {'Authorization': 'Bearer ' + auth_token}
    url = 'https://api-r4l-ventilator-prediction.herokuapp.com/berkeley/severity/auto-upload'
    d.to_csv(csv)
    with open(csv, 'rb') as f:
        r = requests.post(url, files={'file': ('myfile.csv', f, 'text/csv', {'Expires': '0'})}, 
                          headers=hed)
    print('api post succeeded?', r.text)
    


def df_to_plot(df, NUM_DAYS_LIST):
    ks = ['Total Deaths Hospital', 'Hospital Employees', 'Hospital Name', 'CountyName', 'StateName', 'ICU Beds', 'CMS Certification Number', 'countyFIPS']
    remap = {1: 'Low', 2: 'Medium', 3: 'High'}
    for i in NUM_DAYS_LIST:
        ks.append(f'Severity {i}-day')
        ks.append(f'Surge {i}-day')
        ks.append(f'Predicted New Deaths Hospital {i}-day')
        ks.append(f'Predicted Deaths Hospital {i}-day')
        ks.append(f'Severity Index {i}-day')
        df[f'Severity Index {i}-day'] = [remap[x] for x in df[f'Severity {i}-day']]
    ks += ['Surge County 3-day', 'tot_deaths', 'SVIPercentile'] # county keys
    return df[ks]
    
if __name__ == '__main__':
    print('loading data...')
    NUM_DAYS_LIST = [1, 2, 3, 4, 5, 6, 7]
    df_county = load_data.load_county_level(data_dir=oj(parentdir, 'data'))
    df_hospital = load_data.load_hospital_level(data_dir=oj(os.path.dirname(parentdir),
                                                            'covid-19-private-data'))
    df_county = add_preds(df_county, NUM_DAYS_LIST=NUM_DAYS_LIST, cached_dir=oj(parentdir, 'data')) # adds keys like "Predicted Deaths 1-day"
    df = merge_data.merge_county_and_hosp(df_county, df_hospital)
    df = add_severity_index(df, NUM_DAYS_LIST)
    df = df.sort_values('Total Deaths Hospital', ascending=False)
    
    write_to_gsheets_and_api(df, service_file=oj(parentdir, 'creds.json'),
                             api_file=oj(parentdir, 'ian_key.env'))
    print('succesfully wrote to gsheets')
        
    d = df_to_plot(df, NUM_DAYS_LIST)
    print('writing viz index animated...')
    viz_interactive.viz_index_animated(d, [2, 5], out_name=oj(parentdir, 'results', 'hospital_index_animated.html'))
    print('succesfully wrote viz index animated')

    
    # print
    d = datetime.datetime.today()
    print(f'success! {d.month}_{d.day}_{d.hour}')