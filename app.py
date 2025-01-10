from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import sqlite3
from datetime import datetime
import random
import requests
from dotenv import load_dotenv
from urllib.parse import quote
from openai import OpenAI
import base64

# 加载环境变量
try:
    load_dotenv()
except:
    pass

# OpenRouter API配置
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
SITE_URL = os.getenv('SITE_URL', 'http://localhost:5000')
SITE_NAME = os.getenv('SITE_NAME', 'Medical Image Rating System')

# 初始化OpenAI客户端
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# 数据库初始化
def init_db():
    conn = sqlite3.connect('ratings.db')
    c = conn.cursor()
    
    # 先删除旧表（如果存在）
    c.execute('DROP TABLE IF EXISTS ratings')
    
    # 创建新表，评分范围改为1-7
    c.execute('''
        CREATE TABLE IF NOT EXISTS ratings
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         image_id TEXT,
         rater_id TEXT,
         image_quality INTEGER CHECK(image_quality BETWEEN 1 AND 7),
         text_quality INTEGER CHECK(text_quality BETWEEN 1 AND 7),
         consistency INTEGER CHECK(consistency BETWEEN 1 AND 7),
         timestamp DATETIME)
    ''')
    conn.commit()
    conn.close()

app = Flask(__name__)

# 初始化数据库
init_db()

# 加载样本数据
def load_samples():
    samples = []
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    
    # 首先尝试从RefineNet_select_75.json加载
    metadata_path = os.path.join(static_dir, 'RefineNet_select_75.json')
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                for item in metadata:
                    image_filename = item.get('image', '')
                    if image_filename:
                        # 检查图片文件是否存在
                        image_path = os.path.join(static_dir, 'images', image_filename)
                        if os.path.exists(image_path):
                            # 构建正确的图片URL
                            image_url = f'/static/images/{quote(image_filename)}'
                            # 从文本文件读取描述
                            text_content = item.get('text', '')
                            if not text_content:
                                text_file = os.path.join(static_dir, 'texts', f"{os.path.splitext(image_filename)[0]}.txt")
                                if os.path.exists(text_file):
                                    with open(text_file, 'r', encoding='utf-8') as tf:
                                        text_content = tf.read().strip()
                            
                            # 构建新的样本格式
                            sample = {
                                'id': os.path.splitext(image_filename)[0],
                                'image_url': image_url,
                                'text': text_content
                            }
                            samples.append(sample)
                        else:
                            print(f"Warning: Image file not found: {image_path}")
                
                if samples:
                    return samples
                print("Warning: No valid samples found in RefineNet_select_75.json")
        except Exception as e:
            print(f"Error loading RefineNet_select_75.json: {e}")
            import traceback
            traceback.print_exc()
    
    # 如果RefineNet_select_75.json不存在或加载失败，则扫描目录
    images_dir = os.path.join(static_dir, 'images')
    texts_dir = os.path.join(static_dir, 'texts')
    
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)
    if not os.path.exists(texts_dir):
        os.makedirs(texts_dir)
    
    # 获取所有图片文件
    image_files = [f for f in os.listdir(images_dir) if f.endswith(('.jpg', '.png', '.jpeg'))]
    
    for image_file in image_files:
        image_id = os.path.splitext(image_file)[0]  # 获取文件名（不含扩展名）
        text_file = f"{image_id}.txt"
        text_path = os.path.join(texts_dir, text_file)
        
        # 读取对应的文本内容
        text_content = ""
        if os.path.exists(text_path):
            try:
                with open(text_path, 'r', encoding='utf-8') as f:
                    text_content = f.read().strip()
            except Exception as e:
                print(f"Error reading text file {text_file}: {e}")
                text_content = "无法加载文本内容"
        
        # 修改图片URL的生成方式，使用URL编码处理文件名
        image_url = f'/static/images/{quote(image_file)}'
        
        samples.append({
            'id': image_id,
            'image_url': image_url,
            'text': text_content
        })
    
    return samples

@app.route('/static/selected_pairs.json')
def redirect_to_new_json():
    return send_file('static/RefineNet_select_75.json')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/rating')
def rating():
    try:
        samples = load_samples()
        return render_template('rating.html', samples=samples)
    except Exception as e:
        print(f"Error loading samples: {e}")
        return "Error loading samples", 500

@app.route('/submit_rating', methods=['POST'])
def submit_rating():
    data = request.json
    conn = sqlite3.connect('ratings.db')
    c = conn.cursor()
    
    # 从完整路径中提取文件名
    image_id = data['image_id']
    if '/' in image_id:
        image_id = image_id.split('/')[-1]  # 获取路径最后一部分
    if '.jpg' in image_id:
        image_id = image_id.replace('.jpg', '')  # 移除文件扩展名
    
    # 检查是否已存在该评分者对该图片的评分
    c.execute('''
        SELECT id FROM ratings 
        WHERE image_id = ? AND rater_id = ?
    ''', (image_id, data['rater_id']))
    
    existing_rating = c.fetchone()
    
    try:
        # 验证评分范围
        image_quality = int(data['image_quality'])
        text_quality = int(data['text_quality'])
        consistency = int(data['consistency'])
        
        if not (1 <= image_quality <= 7 and 1 <= text_quality <= 7 and 1 <= consistency <= 7):
            raise ValueError("评分必须在1-7分之间")
            
        if existing_rating:
            # 更新现有评分
            c.execute('''
                UPDATE ratings 
                SET image_quality = ?, text_quality = ?, consistency = ?, timestamp = CURRENT_TIMESTAMP
                WHERE image_id = ? AND rater_id = ?
            ''', (
                image_quality,
                text_quality,
                consistency,
                image_id,
                data['rater_id']
            ))
        else:
            # 插入新评分
            c.execute('''
                INSERT INTO ratings (image_id, rater_id, image_quality, text_quality, consistency, timestamp)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                image_id,
                data['rater_id'],
                image_quality,
                text_quality,
                consistency
            ))
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except ValueError as e:
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/clean_ratings/<rater_id>')
def clean_ratings(rater_id):
    try:
        conn = sqlite3.connect('ratings.db')
        c = conn.cursor()
        
        # 获取该评分者的所有评分
        results = c.execute('''
            SELECT id, image_quality, text_quality, consistency
            FROM ratings
            WHERE rater_id = ?
        ''', (rater_id,)).fetchall()
        
        # 清理并更新数据
        for row in results:
            rating_id = row[0]
            # 将分数限制在1-3范围内
            image_quality = min(max(1, min(3, row[1])), 3) if row[1] != 30 else 0
            text_quality = min(max(1, min(3, row[2])), 3) if row[2] != 30 else 0
            consistency = min(max(1, min(3, row[3])), 3) if row[3] != 30 else 0
            
            c.execute('''
                UPDATE ratings
                SET image_quality = ?,
                    text_quality = ?,
                    consistency = ?
                WHERE id = ?
            ''', (image_quality, text_quality, consistency, rating_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": "Ratings cleaned successfully"})
    except Exception as e:
        print(f"Error cleaning ratings: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/export_results/<rater_id>')
def export_results(rater_id):
    try:
        # 确保导出目录存在
        export_dir = 'exports'
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        
        conn = sqlite3.connect('ratings.db')
        c = conn.cursor()
        
        # 获取所有样本
        samples = load_samples()
        
        # 获取该评分者的所有评分
        c.execute('''
            SELECT image_id, image_quality, text_quality, consistency
            FROM ratings
            WHERE rater_id = ?
        ''', (rater_id,))
        
        ratings_data = c.fetchall()
        conn.close()

        if not ratings_data:
            return jsonify({"error": "没有找到评分数据"}), 404

        # 创建评分字典，方便查找
        ratings_dict = {}
        for row in ratings_data:
            image_id = row[0]
            # 处理可能存在的完整路径
            if '/' in image_id:
                image_id = image_id.split('/')[-1]
            if '.jpg' in image_id:
                image_id = image_id.replace('.jpg', '')
            ratings_dict[image_id] = row[1:]

        # 计算每个样本的评分
        results = []
        for sample in samples:
            image_id = sample['id']
            # 获取评分数据，如果没有评分则使用默认值0
            rating = ratings_dict.get(image_id, (0, 0, 0))
            
            results.append({
                'image_id': image_id,
                'image_path': sample['image_url'],
                'text': sample['text'],
                'image_quality': rating[0],
                'text_quality': rating[1],
                'consistency': rating[2],
                'total_score': sum(rating)  # 总分为三个维度的分数之和
            })

        # 生成导出文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'rating_results_{rater_id}.json'
        filepath = os.path.join(export_dir, filename)

        # 保存结果
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'rater_id': rater_id,
                'timestamp': timestamp,
                'results': results,
                'rating_system': {
                    'max_score_per_dimension': 7,
                    'dimensions': ['image_quality', 'text_quality', 'consistency'],
                    'total_max_score': 21
                }
            }, f, ensure_ascii=False, indent=2)

        return send_file(filepath, as_attachment=True)
    except Exception as e:
        print(f"Error exporting results: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/query_ai', methods=['POST'])
def query_ai():
    try:
        data = request.json
        print("Received request data:", data)
        
        request_type = data.get('type', 'explanation')
        print(f"Request type: {request_type}")

        if not OPENROUTER_API_KEY:
            return jsonify({"error": "OpenRouter API key not configured"}), 500

        messages = []
        
        if request_type == 'translation':
            # 翻译请求：直接翻译，不加任何额外内容
            text = data.get('text', '')
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的医学翻译。直接将输入的英文翻译成中文，不要添加任何解释、分析或格式。保持原文的简洁性。"
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
            
        elif request_type == 'rating_assist':
            # 评分辅助：专业的三维度分析
            text = data.get('text', '')
            image_url = data.get('image_url', '')
            
            messages = [
                {
                    "role": "system",
                    "content": """你是医学图文评估专家。请简要分析：
1. 图像质量：清晰度、对比度、细节可见性
2. 文本质量：术语准确性、描述完整性
3. 图文一致性：特征对应关系、信息匹配度

用简短的2-3句话评估每个维度。"""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"请评估以下医学图文对的质量：\n\n{text}"
                        }
                    ]
                }
            ]
            
            # 优化图片处理逻辑
            if image_url and image_url.startswith(('http://', 'https://')):
                messages[1]["content"].append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            elif image_url:
                try:
                    local_path = image_url.replace('http://127.0.0.1:5000/', '').lstrip('/')
                    abs_path = os.path.join(os.path.dirname(__file__), local_path)
                    if os.path.exists(abs_path) and os.path.getsize(abs_path) < 1024 * 1024:  # 限制图片大小为1MB
                        with open(abs_path, 'rb') as img_file:
                            img_data = base64.b64encode(img_file.read()).decode('utf-8')
                            messages[1]["content"].append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
                            })
                except Exception as e:
                    print(f"Error processing image: {e}")
            
        else:
            # 自由文本查询：医学专业问答
            query = data.get('query', '')
            context = data.get('context', '')
            
            messages = [
                {
                    "role": "system",
                    "content": """你是一个专业的医学领域AI助手。请根据用户的问题提供专业、准确的解答。

回答要求：
1. 使用专业、准确的医学术语
2. 保持回答的简洁性和针对性
3. 必要时提供相关的医学背景知识
4. 如果问题不明确，说明需要补充的信息"""
                },
                {
                    "role": "user",
                    "content": query
                }
            ]

        print("Final messages structure:", json.dumps(messages, indent=2))

        # 调用OpenRouter API
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": SITE_URL,
                "X-Title": SITE_NAME,
            },
            model="google/gemini-flash-1.5",
            messages=messages
        )

        response_content = completion.choices[0].message.content
        print("API response content:", response_content)

        return jsonify({
            "response": response_content
        })

    except Exception as e:
        print(f"Error querying AI: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 