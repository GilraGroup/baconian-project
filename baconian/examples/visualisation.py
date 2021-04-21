#from baconian.common.log_data_loader import *
from baconian.common.plotter import Plotter
import pandas as pd
from baconian.common.files import *
from collections import OrderedDict
from typing import Union


if __name__ == "__main__":
    def MultipleExpLogDataLoader(
        exp_root_dir_list='/home/eia17mdw/baconian/baconian/examples/log_path')\
        .plot_res(sub_log_dir_name='record/example_scheduler_agent/TEST',
                  key='sum_reward',
                  index='sample_counter',
                  mode='line',
                  average_over=1,
                  file_name=None,
                  save_format='png',
                  save_path='./')

    # Aditya: for examples from examples folder.
    #exp_root_dir='/home/ac1agi/baconian_examples/log_path'
    #exp_root_dir='/home/eia17mdw/HR_baconian_examples_S2/log_path'
    #log_name = exp_root_dir+'/record/demo_exp_agent/TEST.json'

    # Aditya: for examples from benchmark folder.
    #exp_root_dir='/home/ac1agi/baconian_examples/benchmark_log/Pendulum-v0/dyna/2020-09-07_13-10-09/exp_0'
    #exp_root_dir='/home/eia17mdw/HR_baconian_examples_S2/log_path/Pendulum-v0/dyna/2020-09-07_13-10-09/exp_0'
    #log_name = exp_root_dir+'/record/benchmark_agent/TEST.json'

    key='sum_reward'
    index='sample_counter'
    mode='line'
    average_over=1
    file_name=None
    save_format='png'
    save_path='./'
    save_flag = True
    
    f = open(log_name, 'r')
    res_dict = json.load(f)
    key_list = res_dict[key]
    key_value = OrderedDict()
    key_vector = []
    index_vector = []
    for record in key_list:
        num_index = int(record[index])
        index_vector.append(num_index)
        key_vector.append(record["value"])
    key_value[index] = index_vector
    key_value[key] = key_vector
    data = pd.DataFrame.from_dict(key_value)  # Create dataframe for plotting
    row_num = data.shape[0]
    column_num = data.shape[1]
    data_new = data

    # Calculate mean value in horizontal axis, incompatible with histogram mode
    if average_over != 1:
        if mode != 'histogram':
            new_row_num = int(row_num / average_over)
            data_new = data.head(new_row_num).copy()
            data_new.loc[:, index] = data_new.loc[:, index] * average_over
            for column in range(1, column_num):
                for i in range(new_row_num):
                    data_new.iloc[i, column] = data.iloc[i * average_over: i * average_over + average_over,
                                               column].mean()

    if mode == 'histogram':
        histogram_flag = True
        data_new = data.iloc[:, 1:].copy()
    else:
        histogram_flag = False
    scatter_flag = True if mode == 'scatter' else False

    Plotter.plot_any_key_in_log(data=data_new, index=index, key=key,
                                sub_log_dir_name='',
                                scatter_flag=scatter_flag, save_flag=save_flag,
                                histogram_flag=histogram_flag, save_path=save_path,
                                save_format=save_format, file_name=file_name)
