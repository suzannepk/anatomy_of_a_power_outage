import os
import sys
import time
import math
import datetime
import numpy as np
import pandas as pd
from mpi4py import MPI

# Regions 181G
#   1: Pacific
#   2: Mountain
#   3: West North Central
#   4: West South Central
#   5: East North Central
#   6: East South Central
#   7: New England
#   8: Mid-Atlantic
#   9: South Atlantic
FIPS_TO_STATE = {
    '01': ('Alabama', 6),
    '02': ('Alaska', 1),
    '04': ('Arizona', 2),
    '05': ('Arkansas', 4),
    '06': ('California', 1),
    '08': ('Colorado', 2),
    '09': ('Connecticut', 7),
    '10': ('Delaware', 9),
    '11': ('District of Columbia', 9),
    '12': ('Florida', 9),
    '13': ('Georgia', 9),
    '15': ('Hawaii', 1),
    '16': ('Idaho', 2),
    '17': ('Illinois', 5),
    '18': ('Indiana', 5),
    '19': ('Iowa', 3),
    '20': ('Kansas', 3),
    '21': ('Kentucky', 6),
    '22': ('Louisiana', 4),
    '23': ('Maine', 7),
    '24': ('Maryland', 9),
    '25': ('Massachusetts', 7),
    '26': ('Michigan', 5),
    '27': ('Minnesota', 3),
    '28': ('Mississippi', 6),
    '29': ('Missouri', 3),
    '30': ('Montana', 2),
    '31': ('Nebraska', 3),
    '32': ('Nevada', 2),
    '33': ('New Hampshire', 7),
    '34': ('New Jersey', 8),
    '35': ('New Mexico', 2),
    '36': ('New York', 8),
    '37': ('North Carolina', 9),
    '38': ('North Dakota', 3),
    '39': ('Ohio', 5),
    '40': ('Oklahoma', 4),
    '41': ('Oregon', 1),
    '42': ('Pennsylvania', 8),
    '44': ('Rhode Island', 7),
    '45': ('South Carolina', 9),
    '46': ('South Dakota', 3),
    '47': ('Tennessee', 6),
    '48': ('Texas', 4),
    '49': ('Utah', 2),
    '50': ('Vermont', 7),
    '51': ('Virginia', 9),
    '53': ('Washington', 1),
    '54': ('West Virginia', 9),
    '55': ('Wisconsin', 5),
    '56': ('Wyoming', 2),
}

month_days = {
    1: 31,  # January
    2: 28,  # February (non-leap year)
    3: 31,  # March
    4: 30,  # April
    5: 31,  # May
    6: 30,  # June
    7: 31,  # July
    8: 31,  # August
    9: 30,  # September
    10: 31, # October
    11: 30, # November
    12: 31  # December
}

#latlong = pd.read_csv(f'OtherCSVs/us_county_latlng.csv')
latlong = pd.read_csv(f'../../Project3/Data/OtherCSVs/us_county_latlng.csv')
latlong['fips_code_str'] = latlong['fips_code'].astype(str)

def readEagle(years = [2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021], drop_columns = ['county', 'state']): 
    cleaned_eaglei = pd.DataFrame()
    for year in years:
        #eagle_csv = pd.read_csv(f'../../Project3/Data/eaglei_outages/eaglei_outages_{year}.csv')
        eagle_csv = pd.read_csv(f'../../Project3/Data/eaglei_outages/eaglei_outages_{year}.csv')
        cleaned_eaglei = pd.concat([cleaned_eaglei, eagle_csv], ignore_index = True)
        cleaned_eaglei.drop(drop_columns, axis=1, inplace=True)    # Leaves fips, sum, run_start_time
    
    return cleaned_eaglei

# Function to determine the range of fips code my rank should work with
def fipsRange(df, Rank, Size):
    # Create a list of each unique fips code
    fips = list(df['fips_code'].unique())

    # Determine indices for fips code selection by rank
    WorkLoadPerProc = len(fips) // Size
    Remainder = len(fips) % Size
    StartIndx = Rank * WorkLoadPerProc + min(Rank, Remainder)
    EndIndx = StartIndx + WorkLoadPerProc + (1 if Rank < Remainder else 0)

    return StartIndx, EndIndx, fips

def fipsToState(fip):      
    str_fip = str(fip)

    # Check if fip is missing leading 0
    if len(str_fip) < 5:
        str_fip = '0' + str_fip
    
    if not (latlong['fips_code_str'].isin([str_fip]).any() | latlong['fips_code_str'].isin([str_fip[1:]]).any()):
        # print(f"Here and fip is: {fip}. Fip type is: {type(fip)}.")
        return 'skip', 'skip', 'skip'
        
    st_num = str_fip[0:2]

    # Return the state name, region id, and state id based on the first two fips digits
    if st_num in FIPS_TO_STATE:    
        return FIPS_TO_STATE[st_num][0], FIPS_TO_STATE[st_num][1], st_num
    else:
        return 'skip', 'skip', 'skip'

def get_days_in_month(month, year):
    if month == 2:  # February
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            return 29  # Leap year
        else:
            return 28  # Non-leap year
    return month_days.get(month, 0)

def circular_toy(toy):

    x = (2*math.pi*(toy-1)) / 12
    toy_sin = math.sin(x)
    toy_cos = math.cos(x)
    
    return toy_sin, toy_cos

# Returns the time of year as a float between 1.0 and 12.9999999
def time_of_year(dt_object):
    
  # Calculate the number of days in the month
  days_in_month = get_days_in_month(dt_object.month, dt_object.year) #(datetime.date(dt_object.year, dt_object.month + 1, 1) - datetime.date(dt_object.year, dt_object.month, 1)).days

  # Calculate the fraction of the month
  fraction_of_month = (dt_object.day - 1 + dt_object.hour / 24 + dt_object.minute / (24 * 60) + dt_object.second / (24 * 3600)) / days_in_month

  # Combine month and fraction of month
  toy = dt_object.month + fraction_of_month

  toy_sin, toy_cos = circular_toy(toy)
    
  return toy, toy_sin, toy_cos

# Aggregate individual timestamped outages into continuous outage times
def aggregateOutages(outages, fips, length_filter=0.0):
    
    # Create empty dataframe for outage ranges 
    features = ["State", "FIPS", "StateNum", "Region", "Lat", "Long", "Month", "Month_Sin", "Month_Cos", "OutageStart", "OutageEnd", "OutageLength", "Sum"]
    fip_outage_ranges = pd.DataFrame(columns=features)

    #Look through all of my rank's fips codes and determine the continuous outages
    for fip in fips:
        # Find this fip's outage times
        fip_outage_df = outages[fip]

        # Reset the indices starting at 0 for looping
        fip_outage_df.reset_index(inplace=True)
        datetimes = pd.to_datetime(fip_outage_df['run_start_time'])
        fip_outage_df = pd.concat([fip_outage_df, datetimes.rename('datetime')], axis=1)
    
        state, region, st_num = fipsToState(fip)
        if state == 'skip':
            continue
        start = "None"
        end = "None"

        sum = 0
        sumcount = 0

        for i in range(len(fip_outage_df['datetime'])-1):
            # If no start time add start
            if(start == "None"):
                start = fip_outage_df['datetime'][i]

            sum += fip_outage_df['sum'][i]
            sumcount += 1
            
            # If next time is continuous, continue
            if(fip_outage_df['datetime'][i] + datetime.timedelta(minutes=15) == fip_outage_df['datetime'][i+1]):
                continue
            # Otherwise, this is the end of this outage. Add it as the end time and append it to this fips' outage range list
            else:
                end = fip_outage_df['datetime'][i]
                length = (end - start).total_seconds() / 3600
                # Only record if outage lasts beyond time_range
                if length > length_filter:
                    month, month_sin, month_cos = time_of_year(start)
                    fip_outage_ranges.loc[len(fip_outage_ranges)] = {"State": state, "FIPS": fip, "StateNum": st_num, "Region": region, "Lat":latlong[latlong['fips_code']==fip]['lat'].iloc[0], "Long":latlong[latlong['fips_code']==fip]['lng'].iloc[0], "Month": month, "Month_Sin": month_sin, "Month_Cos": month_cos, "OutageStart": start, "OutageEnd": end, "OutageLength": length, "Sum": (sum/sumcount)}
                sum = 0
                sumcount = 0
                start = "None"
                end = "None"

    return fip_outage_ranges

def Outage(DataFrame, Rank, Size, length=0.0):
    # Find range of fips codes I should look at based on my rank
    StartIndx, EndIndx, FipsCodeList = fipsRange(DataFrame, Rank, Size)

    # Pick the fips codes I should be looking at in this rank
    myFips = FipsCodeList[StartIndx:EndIndx]

    # Finding each fips' threshold of customers to classify an outage
    fipsOutageSum = {fips: DataFrame[DataFrame['fips_code'] == fips]['sum'].max() // 10 for fips in myFips}
   
    # Find all dates which classify as an outage for each fips code
    fipsOutageDates = {}
    for fips in myFips:
        temp = DataFrame[DataFrame['fips_code'] == fips]
        fipsOutageDates[fips] = temp[temp['sum'] >= fipsOutageSum[fips]]

    aggregated_outages = aggregateOutages(fipsOutageDates, myFips, length)

    return aggregated_outages   #.reset_index(drop=True, inplace=True)

def main(args):
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    if rank == 0:
        # Record the start time for time tracking
        start_time = MPI.Wtime() 
        years = []

        # Argument handling
        if len(args) < 2:
            print(f"error: {args[0]} [<years>] <outage_length>")
            return 1
        if len(args) >= 3:
            start_year=args[1]
            end_year=args[len(args)-2]
            for i in range(1, len(args)-1):
                years.append(args[i])
        if years:
            cleaned_eaglei = readEagle(years = years)
        else:
            cleaned_eaglei = readEagle()
    else:
        cleaned_eaglei = pd.DataFrame()

    # Broadcast the initial data to all ranks
    cleaned_eaglei = comm.bcast(cleaned_eaglei, root=0) 

    # Utilize MPI to split the data amongst the ranks and perform our processing
    agg_outages_per_proc = Outage(cleaned_eaglei, rank, size, float(args[len(args)-1]))

    # Gather all the modified data back to rank 0
    aggregated_Outages = comm.gather(agg_outages_per_proc, root=0)

    # Record data in a CSV and report total MPI time
    if(rank == 0):
    
        end_time = MPI.Wtime()
        
        aggOutagesDF = pd.concat(aggregated_Outages)
    
        aggOutagesDF.sort_values(by=['State', 'OutageStart'], inplace=True)
    
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        aggOutagesDF.to_csv(f'Data/OutageCSVs/{start_year}-{end_year}-Outages.csv', index=False, header=True)
        print(f"Total time: {end_time - start_time} seconds")

if __name__ == "__main__":
    main(sys.argv)
