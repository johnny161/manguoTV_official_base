#!/usr/bin/env python
# coding: utf-8

# In[1]:


# -*- coding: utf-8 -*- 
from hdfs import Client
import sys
import random
#reload(sys)
#sys.setdefaultencoding("utf-8")

import pandas as pd
import logging
import os
import io
import glob
import numpy as np
import pandas as pd
from collections import defaultdict
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
import gc
pd.set_option('display.min_rows',None)
from sklearn.metrics import roc_curve,auc,roc_auc_score
from sklearn.model_selection import train_test_split
from tqdm import tqdm_notebook
import time


# In[2]:


def isNan_2(a):
    return a != a


def reduce_mem_usage(df, verbose=True):
    numerics = ['int16', 'int32', 'int64', 'float16', 'float32', 'float64']
    start_mem = df.memory_usage().sum() / 1024**2    
    cols_ = [col for col in list(df) if col not in ['cid', 'vid']]
    for col in cols_:
        col_type = df[col].dtypes
        if col_type in numerics:
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                       df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)  
            else:
                if c_min > np.finfo(np.float16).min and c_max < np.finfo(np.float16).max:
                    df[col] = df[col].astype(np.float16)
                elif c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astype(np.float64)    
    end_mem = df.memory_usage().sum() / 1024**2
    if verbose: print('Mem. usage decreased to {:5.2f} Mb ({:.1f}% reduction)'.format(end_mem, 100 * (start_mem - end_mem) / start_mem))
    return df



def timestamp_to_date (timestamp) :
    # ???????????????????????????
    #???????????????????????????,???:"%Y-%m-%d %H:%M:%S"
    timeArray = time.localtime(int(timestamp))
    otherStyleTime = time.strftime("%Y-%m-%d %H:%M:%S", timeArray)
    return otherStyleTime

def date_2_timestamp (date_time) :
    # ?????????????????????
    # ??????????????????
    timeArray = time.strptime(date_time, "%Y%m%d%H%M%S")    
    # ???????????????
    timeStamp = np.int64(time.mktime(timeArray))
    return timeStamp  # 1381419600

def get_candidate_recall (recall_list, candidate_vid_set) :
    result = []
    for recall in recall_list :
        if recall in candidate_vid_set :
            result.append(recall)
            
    return result 

#?????????did-fvid
def get_candidate_did_fvid (df_click, df_vid_info) :
    candidate_did_fvid = df_click[['did', 'fvid']].drop_duplicates().reset_index(drop=True)
    candidate_did_fvid = candidate_did_fvid.merge(df_vid_info[['vid', 'cid']].rename(columns = {'vid' : 'fvid'}), on='fvid', how='left')
    return candidate_did_fvid

#?????????vid
def get_candidate_vid (df_click, df_vid_info) :
    candidate_vid = df_click[['vid']].drop_duplicates().reset_index(drop=True)
    candidate_vid = candidate_vid.merge(df_vid_info[['vid', 'cid', 'online_time']], on='vid', how='left')
    return candidate_vid


# In[3]:


df_click_data_set = []
df_show_data_set = []
df_main_vv_set = []

base_path = "/home/THLUO/competition/A_CSV/"

for part in tqdm_notebook(['part_1', 'part_2', 'part_3', 'part_4', 'part_5', 'part_6', 'part_7']) :
    df_click_data = pd.read_csv(base_path + "{}/dbfeed_click_info.csv".format(part))
    df_show_data = pd.read_csv(base_path + "{}/dbfeed_show_info.csv".format(part))
    #df_main_vv = pd.read_pickle("/home/THLUO/competition/A2/{}/user_main_behavior.pkl".format(part))
    #del df_click_data['vid_hb']
    #del df_click_data['duration']
    #del df_click_data['cid']
    df_click_data_set.append(df_click_data)
    df_show_data_set.append(df_show_data)
    
    
df_show_data = pd.concat(df_show_data_set).reset_index(drop=True)
df_click_data = pd.concat(df_click_data_set).reset_index(drop=True)


# In[4]:


#?????????????????????
df_vid_info = pd.read_csv(base_path + "vid_info.csv")
#df_vid_info['online_time'] = df_vid_info['online_time'].apply(lambda x : np.NaN if x <= 0 else x)
#?????????????????????
df_vid_tag_conf = pd.read_csv(base_path + "vid_stars_info.csv")
#???????????????????????????
df_vid_dim_tags_conf = pd.read_csv(base_path + "vid_dim_tags_info.csv")
#?????????????????????
df_dim_tag_conf = pd.read_csv(base_path + "dim_tags_info.csv")

df_click_data = df_click_data.merge(df_vid_info[['vid', 'cid']], on='vid', how='left')
df_show_data = df_show_data.merge(df_vid_info[['vid', 'cid']], on='vid', how='left')

df_show_data['date'] = df_show_data['time'].apply(timestamp_to_date).apply(lambda x : x.split(' ')[0])
df_click_data['date'] = df_click_data['time'].apply(timestamp_to_date).apply(lambda x : x.split(' ')[0])


# In[5]:


#?????????did, fvid?????????
train_click = df_click_data[(df_click_data['date'] == '2021-03-25')].reset_index(drop=True)
train_candidate_did_fvid = get_candidate_did_fvid(train_click, df_vid_info)
#?????????vid?????????
train_candidate_vid = get_candidate_vid(train_click, df_vid_info)

#?????????did, fvid?????????
valid_click = df_click_data[(df_click_data['date'] == '2021-03-26')].reset_index(drop=True)
valid_candidate_did_fvid = get_candidate_did_fvid(valid_click, df_vid_info)
#?????????vid?????????
valid_candidate_vid = get_candidate_vid(valid_click, df_vid_info)

#?????????did, fvid?????????
test_candidate_did_fvid = pd.read_csv(base_path + "/part_test/test_candidate_did_fvid.csv")
#?????????vid?????????
test_candidate_vid = pd.read_csv(base_path + "/part_test/test_candidate_vid.csv")
test_candidate_did_fvid = test_candidate_did_fvid.merge(df_vid_info[['vid', 'cid']].rename(columns={"vid" : "fvid"}), on='fvid', how='left')
test_candidate_vid = test_candidate_vid.merge(df_vid_info[['vid', 'cid']], on='vid', how='left')


# In[11]:


#??????N???fvid??????topN?????????????????????
def recall_by_fvid_topN_ctr (df_click, df_show, topN, recall_name, start_date, end_date) :
    df_click = df_click[(df_click['date'] >= start_date) & (df_click['date'] < end_date)]
    df_fvid_vid_clicks = df_click.groupby(['fvid', 'vid'])['pos'].count().reset_index().rename(columns={'pos' : 'click_counts'})
    df_fvid_vid_clicks['click_rank'] = df_fvid_vid_clicks.groupby('fvid')['click_counts'].rank(method='dense', ascending=False)
    
    df_show = df_show[(df_show['date'] >= start_date) & (df_show['date'] < end_date)]
    df_fvid_vid_shows = df_show.groupby(['fvid', 'vid'])['pos'].count().reset_index().rename(columns={'pos' : 'show_counts'})
    df_fvid_vid_clicks = df_fvid_vid_clicks.merge(df_fvid_vid_shows, on=['fvid', 'vid'], how='left')
    df_fvid_vid_clicks['vid_ctr'] = df_fvid_vid_clicks['click_counts'] / (df_fvid_vid_clicks['show_counts'])
    df_fvid_vid_clicks['ctr_rank'] = df_fvid_vid_clicks.groupby('fvid')['vid_ctr'].rank(method='dense', ascending=False)    
    
    #??????N??????fvid????????????????????????N?????????
    df_recall = df_fvid_vid_clicks[df_fvid_vid_clicks['ctr_rank'] <= topN]
    df_recall = df_recall.groupby('fvid')['vid'].agg(lambda x : list(x)).reset_index().rename(columns={'vid' : recall_name})
    
    return df_recall

#??????N???fvid??????topN????????????????????????
def recall_by_fvid_topN_vts_ratio (df_click, topN, recall_name, start_date, end_date) :
    df_click = df_click[(df_click['date'] >= start_date) & (df_click['date'] < end_date)]
    df_fvid_vid_hb_ratio = df_click.groupby(['fvid', 'vid'])['vts_ratio'].sum().reset_index().rename(columns={'vts_ratio' : 'vid_sum_vts_ratio'})
    df_fvid_vid_hb_ratio['vid_sum_vts_ratio_rank'] = df_fvid_vid_hb_ratio.groupby('fvid')['vid_sum_vts_ratio'].rank(method='dense', ascending=False)
         
    #??????N??????fvid???????????????????????????N?????????
    df_recall = df_fvid_vid_hb_ratio[df_fvid_vid_hb_ratio['vid_sum_vts_ratio_rank'] <= topN]
    df_recall = df_recall.groupby('fvid')['vid'].agg(lambda x : list(x)).reset_index().rename(columns={'vid' : recall_name})    
    return df_recall


# In[12]:


def recall_by_history (df_click_data, df_show_data, candidate_vid, topN, start_date, end_date) :
    candidate_vid_set = set(candidate_vid['vid'].unique())
    #??????N???fvid??????topN?????????????????????
    df_recall_1 = recall_by_fvid_topN_ctr (df_click_data, df_show_data, topN, 'topN_fvid_vid_ctr', start_date, end_date)
    #??????N???fvid??????????????????????????????
    df_recall_2 = recall_by_fvid_topN_vts_ratio (df_click_data, topN, 'topN_fvid_vid_vts_ratio', start_date, end_date)
    
    #??????
    df_recall = df_recall_1.merge(df_recall_2, on='fvid', how='outer')

    df_recall['topN_fvid_vid_ctr'] = df_recall['topN_fvid_vid_ctr'].fillna(0).apply(lambda x : [] if x == 0 else x)
    df_recall['topN_fvid_vid_vts_ratio'] = df_recall['topN_fvid_vid_vts_ratio'].fillna(0).apply(lambda x : [] if x == 0 else x)

    #?????????
    df_recall['recall_list'] = (df_recall['topN_fvid_vid_ctr'] + df_recall['topN_fvid_vid_vts_ratio'] ).apply(set).apply(list)

    #???????????????vid????????????
    df_recall['recall_list'] = df_recall['recall_list'].apply(get_candidate_recall, args=(candidate_vid_set, ))
    return df_recall


# In[13]:


#??????N????????????(??????????????????????????????????????????????????????)
def recall_by_hot_data (df_click, df_show, candidate_vid, hotN, start_date, end_date) :
    df_click = df_click[(df_click['date'] >= start_date) & (df_click['date'] < end_date)]
    #??????N??????fvid??????vid????????????????????????
    df_fvid_vid_clicks = df_click.groupby(['fvid', 'vid'])['pos'].count().reset_index().rename(columns={'pos' : 'click_counts'})
    
    #??????N??????fvid??????vid????????????????????????
    df_fvid_vid_vts_ratio = df_click.groupby(['fvid', 'vid'])['vts_ratio'].sum().reset_index().rename(columns={'vts_ratio' : 'vid_sum_vts_ratio'})

    #??????????????????????????????????????????N??????????????????
    df_top_click_vid = df_fvid_vid_clicks.groupby('vid')['click_counts'].sum().reset_index().sort_values('click_counts', ascending=False).reset_index(drop=True)
    df_top_click_vid = df_top_click_vid.merge(candidate_vid, on='vid', how='inner')
    #??????????????????????????????????????????????????????N??????????????????
    df_top_vts_ratio_vid = df_fvid_vid_vts_ratio.groupby('vid')['vid_sum_vts_ratio'].sum().reset_index().sort_values('vid_sum_vts_ratio', ascending=False).reset_index(drop=True)
    df_top_vts_ratio_vid = df_top_vts_ratio_vid.merge(candidate_vid, on='vid', how='inner')
    #?????????
    hot_vid_recall = list(df_top_click_vid['vid'].values[:hotN])+ list(df_top_vts_ratio_vid['vid'].values[:hotN])
    hot_vid_recall = list(set(hot_vid_recall))    
    return hot_vid_recall

def recall_by_hot (train_data, df_click_data, df_show_data, candidate_vid, start_date, end_date, hotN) :
    #????????????N??????topN????????????
    hot_vid_recall = recall_by_hot_data (df_click_data, df_show_data, candidate_vid, hotN, start_date, end_date)
    #????????????????????????????????????
    train_data['recall_list'] = train_data['recall_list'].apply(lambda x : list(set(x + hot_vid_recall)))
    return train_data


# In[22]:


def recall (candidate_vid, candidate_did_fvid, df_click, df_show, start_date, end_date, topN = 10) :
    #???N???fvid??????vid??????????????????????????????TOPN????????????
    df_recall = recall_by_history(df_click, df_show, candidate_vid, topN, start_date, end_date)

    data_recall_list = candidate_did_fvid.merge(df_recall, on='fvid', how='left')
    data_recall_list['recall_list'] = data_recall_list['recall_list'].apply(lambda x : [] if isNan_2(x) else x)
    
    #???N????????????(vid?????????????????????????????????TOPN????????????)
    data_recall_list = recall_by_hot (data_recall_list, df_click, df_show, candidate_vid, start_date, end_date, 40)

    data = explode_df(data_recall_list)
    df_click['label'] = 1
    data = data.merge(df_click[df_click['date'] == end_date][['did', 'fvid', 'vid', 'label']], on=['did', 'fvid', 'vid'], how='left')
    data['label'].fillna(0, inplace=True)
    
    return data


# In[23]:


def explode_df(train_data) :
    did_list = []
    fvid_list = []
    vid_list = []
    for row in train_data[['did', 'fvid', 'recall_list']].values :
        did = row[0]
        fvid = row[1]
        recall_list = row[2]
        for recall in recall_list :
            did_list.append(did)
            fvid_list.append(fvid)
            vid_list.append(recall)

    df = pd.DataFrame()
    df['did'] = did_list
    df['fvid'] = fvid_list
    df['vid'] = vid_list
    return df 


# In[24]:


#????????????????????????
data_train = recall(train_candidate_vid, train_candidate_did_fvid, df_click_data, df_show_data, "2021-03-20", "2021-03-25").drop_duplicates().reset_index(drop=True)
data_valid = recall(valid_candidate_vid, valid_candidate_did_fvid, df_click_data, df_show_data, "2021-03-21", "2021-03-26").drop_duplicates().reset_index(drop=True)
data_test = recall(test_candidate_vid, test_candidate_did_fvid, df_click_data, df_show_data, "2021-03-22", "2021-03-27").drop_duplicates().reset_index(drop=True)


# In[26]:


def get_user_click_feat(df_click, key, start_date, end_date) :
    df_feats = df_click.groupby('did')[key].nunique()
    return df_feats

def get_user_show_feat(df_show, key, start_date, end_date) :
    df_feats = df_show.groupby('did')[key].nunique()
    return df_feats

def get_fvid_click_feats (df_click, key, start_date, end_date) :
    df_feats = df_click.groupby('fvid')[key].nunique()
    return df_feats    

def get_fvid_show_feats (df_show, key, start_date, end_date) :
    df_feats = df_show.groupby('fvid')[key].nunique()
    return df_feats 

def get_vid_click_feats (df_click, key, start_date, end_date) :
    df_feats = df_click.groupby('vid')[key].nunique()
    return df_feats 

def get_vid_show_feats (df_show, key, start_date, end_date) :
    df_feats = df_show.groupby('vid')[key].nunique()
    return df_feats

def get_cid_click_feats (df_click, key, start_date, end_date) :
    df_feats = df_click.groupby('cid')[key].nunique()
    return df_feats 

def get_cid_show_feats (df_show, key, start_date, end_date) :
    df_feats = df_show.groupby('cid')[key].nunique()
    return df_feats

def get_user_cross_click_feats (df_click, key, start_date, end_date) :
    df_feats = df_click.groupby(['did', key])['pos'].count().reset_index().rename(columns = {'pos' : 'did_{}_click_counts'.format(key)})   
    return df_feats

def get_fvid_cross_click_feats (df_click, key, start_date, end_date) :
    df_feats = df_click.groupby(['fvid', key])['pos'].count().reset_index().rename(columns = {'pos' : 'fvid_{}_click_counts'.format(key)})   
    return df_feats   


# In[27]:


def make_features (data, candidate_did_fvid, start_date, end_date) :
    data = data.merge(df_vid_info, on='vid', how='left')
    
    df_click = df_click_data[(df_click_data['date'] >= start_date) & (df_click_data['date'] < end_date)]
    df_show = df_show_data[(df_show_data['date'] >= start_date) & (df_show_data['date'] < end_date)]
    
    #??????????????????????????????fvid
    df_did_click_unique_fvid = get_user_click_feat(df_click, 'fvid', start_date, end_date)
    data['did_click_unique_fvid'] = data['did'].map(df_did_click_unique_fvid)
    #??????????????????????????????vid
    df_did_click_unique_vid = get_user_click_feat(df_click, 'vid', start_date, end_date)
    data['did_click_unique_vid'] = data['did'].map(df_did_click_unique_vid)
    #??????????????????????????????cid
    df_did_click_unique_cid = get_user_click_feat(df_click, 'cid', start_date, end_date)
    data['did_click_unique_cid'] = data['did'].map(df_did_click_unique_cid)
    #??????????????????????????????vid
    df_did_show_unique_vid = get_user_show_feat(df_show, 'vid', start_date, end_date)
    data['did_show_unique_vid'] = data['did'].map(df_did_show_unique_vid)
    #??????????????????????????????cid
    df_did_show_unique_cid = get_user_show_feat(df_show, 'cid', start_date, end_date)
    data['did_show_unique_cid'] = data['did'].map(df_did_show_unique_cid)

    #?????????fvid????????????????????????
    df_fvid_click_unique_did = get_fvid_click_feats(df_click, 'did', start_date, end_date)
    data['fvid_click_unique_did'] = data['fvid'].map(df_fvid_click_unique_did)
    #?????????fvid????????????????????????
    df_fvid_show_unique_did = get_fvid_show_feats(df_show, 'did', start_date, end_date) 
    data['fvid_show_unique_did'] = data['fvid'].map(df_fvid_show_unique_did)

    #?????????vid????????????????????????
    df_vid_click_unique_did = get_vid_click_feats(df_click, 'did', start_date, end_date)
    data['vid_click_unique_did'] = data['vid'].map(df_vid_click_unique_did)
    #?????????vid????????????????????????
    df_vid_show_unique_did = get_vid_show_feats(df_show, 'did', start_date, end_date) 
    data['vid_show_unique_did'] = data['vid'].map(df_vid_show_unique_did)

    #?????????cid????????????????????????
    df_cid_click_unique_did = get_cid_click_feats(df_click, 'did', start_date, end_date) 
    data['cid_click_unique_did'] = data['cid'].map(df_cid_click_unique_did)
    #?????????cid????????????????????????
    df_cid_show_unique_did = get_cid_show_feats(df_show, 'did', start_date, end_date) 
    data['cid_show_unique_did'] = data['cid'].map(df_cid_show_unique_did)

    #?????????????????????fvid?????????
    df_did_fvid_clicks = get_user_cross_click_feats(df_click, 'fvid', start_date, end_date)
    data = data.merge(df_did_fvid_clicks, on=['did', 'fvid'], how='left')
    #?????????????????????vid?????????
    df_did_vid_clicks = get_user_cross_click_feats(df_click, 'vid', start_date, end_date)
    data = data.merge(df_did_vid_clicks, on=['did', 'vid'], how='left')
    #?????????????????????cid?????????
    df_did_cid_clicks = get_user_cross_click_feats(df_click, 'cid', start_date, end_date)
    data = data.merge(df_did_cid_clicks, on=['did', 'cid'], how='left')

    #?????????fvid??????vid???????????????
    df_fvid_vid_clicks = get_fvid_cross_click_feats(df_click, 'vid', start_date, end_date)
    data = data.merge(df_fvid_vid_clicks, on=['fvid', 'vid'], how='left')
    #?????????fvid??????cid???????????????
    df_fvid_cid_clicks = get_fvid_cross_click_feats(df_click, 'cid', start_date, end_date)
    data = data.merge(df_fvid_cid_clicks, on=['fvid', 'cid'], how='left')
    
    #???????????????????????????????????????
    df_current_did_cid_clicks = candidate_did_fvid.groupby(['did', 'cid'])['fvid'].count().reset_index().rename(columns = {'fvid' : 'current_did_cid_clicks'})
    data = data.merge(df_current_did_cid_clicks, on=['did', 'cid'], how='left')
    
    data.fillna(0, inplace=True)

    return data


# In[28]:


print ("????????????????????????")
train_data = make_features(data_train, train_candidate_did_fvid, "2021-03-20", "2021-03-25")
print ("????????????????????????")
valid_data = make_features(data_valid, valid_candidate_did_fvid, "2021-03-21", "2021-03-26")
print ("????????????????????????")
test_data = make_features(data_test, test_candidate_did_fvid, "2021-03-22", "2021-03-27")

train_data = reduce_mem_usage(train_data)
valid_data = reduce_mem_usage(valid_data)
test_data = reduce_mem_usage(test_data)


# In[29]:


useless_cols = ['label', 'did', 'online_time', 'preds', 'preds_rank', 'vts_ratio', 'vid_vts', 'key_word']
features = train_data.columns[~train_data.columns.isin(useless_cols)].values
print (features)


params = {
    'objective': 'binary', #?????????????????????
    'metric': {'auc'},
    'boosting_type' : 'gbdt',

    'learning_rate': 0.05,
    'max_depth' : 12,
    'num_leaves' : 2 ** 6,

    'min_child_weight' : 10,
    'min_data_in_leaf' : 40,

    'feature_fraction' : 0.70,
    'subsample' : 0.75,
    'seed' : 114,

    'nthread' : -1,
    'bagging_freq' : 1,
    'verbose' : -1,
    #'scale_pos_weight':200
}


trn_data = lgb.Dataset(train_data[features], label=train_data['label'].values)
val_data = lgb.Dataset(valid_data[features], label=valid_data['label'].values)
print ("train_data : ", train_data.info())
print ("valid_data : ", valid_data.info())
clf = lgb.train(params,
                trn_data,
                3000,
                valid_sets=[trn_data, val_data],
                verbose_eval=50,
                early_stopping_rounds=50)#, feval=self_gauc)


valid_data['preds'] = clf.predict(valid_data[features], num_iteration=clf.best_iteration)
valid_data = valid_data.sort_values(by=['did', 'fvid', 'preds'], ascending=False).reset_index(drop=True)
valid_data['preds_rank'] = valid_data.groupby(['did', 'fvid'])['vid'].cumcount() + 1

valid_solution = valid_data[valid_data['preds_rank'] <= 30][['did', 'fvid', 'vid']]
valid_solution['vts_ratio'] = 1
valid_solution = valid_solution.drop_duplicates(['did', 'fvid', 'vid']).reset_index(drop=True)


# In[30]:


def AP_N (actual_vids, pred_vids, N) :
    if len(pred_vids) > N :
        return 0
    down = np.min([len(actual_vids), N])
    actual_vids = set(actual_vids)
    up,flag,correct = 0,0,0
    for pv in pred_vids :
        if flag > N :
            break
        flag += 1
        if pv in actual_vids :
            correct += 1
            up += float(correct) / flag
    
    return float(up) / down 


#MAP@6??????
def cal_map (df_answer, df_solution) :
    df_A_map_6 = df_answer.groupby(['did', 'fvid'])['vid'].apply(list).reset_index()
    test_solution_map_6 = df_solution.groupby(['did', 'fvid'])['vid'].apply(list).reset_index()
    test_solution_map_6.rename(columns = {'vid' : 'pred_vid'}, inplace=True)
    df_A_map_6 = df_A_map_6.merge(test_solution_map_6, on=['did', 'fvid'], how='left')    
    return df_A_map_6.apply(lambda x : AP_N(x["vid"], x["pred_vid"], 30),axis=1).mean()


#Task2??????
def cal_task2_score (df_answer, df_solution) :
    test_t2 = df_answer.merge(df_solution, on=['did', 'fvid', 'vid'], how='left')
    test_t2 = test_t2.rename(columns = {'vts_ratio_x' : 'actual_vts_ratio'}).rename(columns = {'vts_ratio_y' : 'pred_vts_ratio'})
    df_score = test_t2[test_t2['pred_vts_ratio'].notnull()].reset_index(drop=True)
    df_score['T2_Score'] = 1 / (1 + np.sqrt(np.abs(df_score['actual_vts_ratio'] - df_score['pred_vts_ratio'])))
    df_score = df_score.groupby(['did', 'fvid'])['T2_Score'].sum().reset_index()
    df_temp = df_answer.groupby(['did', 'fvid'])['vid'].count().reset_index()
    df_score = df_temp.merge(df_score, on=['did', 'fvid'], how='left')
    df_score['T2_Score'].fillna(0, inplace=True)
    df_score['T2_Score'] = df_score['T2_Score'] / df_score['vid']
    S = len(df_answer.drop_duplicates(['did', 'fvid']))
    t2_score = float(df_score['T2_Score'].sum()) / float(S)
    return t2_score 


# In[31]:


#??????????????????
df_valid_answer = valid_click.groupby(['did', 'fvid', 'vid'])['vts_ratio'].sum().reset_index()
df_valid_answer['vts_ratio'] = df_valid_answer['vts_ratio'].apply(lambda x : 1 if x >= 1 else x).apply(lambda x : 0 if x <= 0 else x)
map_6 = cal_map(df_valid_answer, valid_solution)
task_2 = cal_task2_score(df_valid_answer, valid_solution)
print (map_6 * 0.7 + task_2 * 0.3)


# In[32]:


useless_cols = ['label', 'did', 'online_time', 'preds', 'preds_rank', 'vts_ratio', 'vid_vts', 'key_word']
features = valid_data.columns[~valid_data.columns.isin(useless_cols)].values
print (features)


trn_data = lgb.Dataset(valid_data[features], label=valid_data['label'].values)
print ("train_data : ", train_data.info())
clf = lgb.train(params,
                trn_data,
                clf.best_iteration,
                valid_sets=[trn_data],
                verbose_eval=50,
                early_stopping_rounds=50)#, feval=self_gauc)



test_data['preds'] = clf.predict(test_data[features], num_iteration=clf.best_iteration)
test_data = test_data.sort_values(by=['did', 'fvid', 'preds'], ascending=False).reset_index(drop=True)
test_data['preds_rank'] = test_data.groupby(['did', 'fvid'])['vid'].cumcount() + 1

test_solution = test_data[test_data['preds_rank'] <= 30][['did', 'fvid', 'vid']]
test_solution['vts_ratio'] = 1
test_solution = test_solution.drop_duplicates(['did', 'fvid', 'vid']).reset_index(drop=True)

test_solution.to_csv('test_solution.csv', index=None)


# In[ ]:





# In[ ]:




