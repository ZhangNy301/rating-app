import pandas as pd
import numpy as np
from scipy import stats
import json
import os

# 读取selected_pairs.json获取模型排名
base_path = "exports"
with open(os.path.join(base_path, 'selected_pairs.json'), 'r', encoding='utf-8') as f:
    selected_pairs = json.load(f)
    
# 创建模型排名字典
model_ranks = {item['image'].split('.')[0]: item['stratified_rank'] for item in selected_pairs}

# 读取每个评分者的数据并计算相关性
raters = ['ZhangNingyi', 'Xiexinyu', 'QianXin', 'LiangZhichao', 'GaoJie']
correlations = {}

for rater in raters:
    filename = os.path.join(base_path, f'rating_results_{rater}.json')
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
        # 创建该评分者的排名字典
        rater_ranks = {item['image_id']: item['rank'] for item in data['results']}
        
        # 准备配对的排名数据
        paired_ranks = []
        for image_id in rater_ranks.keys():
            paired_ranks.append({
                'image_id': image_id,
                'rater_rank': rater_ranks[image_id],
                'model_rank': model_ranks[image_id]
            })
        
        # 转换为DataFrame
        df = pd.DataFrame(paired_ranks)
        
        # 计算Spearman相关系数
        correlation, p_value = stats.spearmanr(df['rater_rank'], df['model_rank'])
        correlations[rater] = {
            'correlation': correlation,
            'p_value': p_value
        }

# 输出结果
print("\n各评分者与模型排名的Spearman相关系数：")
results_df = pd.DataFrame.from_dict(correlations, orient='index')
results_df = results_df.sort_values('correlation', ascending=False)
print(results_df)

# 找出相关性最高的评分者
print("\n相关性最高的评分者：")
top_raters = results_df.head(3)
print(top_raters)

# 找出显著相关的评分者（p < 0.05）
print("\n统计显著的评分者（p < 0.05）：")
significant_raters = results_df[results_df['p_value'] < 0.05]
print(significant_raters)