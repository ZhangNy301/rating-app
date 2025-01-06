# Rating App

这是一个基于 Flask 的图文评分应用程序。用户可以对图片和相关文本进行评分，包括图片质量、文本质量和一致性三个维度。

## 功能特点

- 支持图片和文本的展示
- 提供三个维度的评分系统
- 支持评分数据的导出
- 集成 AI 辅助解释功能

## 安装和运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 设置环境变量：
创建 `.env` 文件并设置必要的环境变量：
```
DEEPSEEK_API_KEY=your_api_key
```

3. 运行应用：
```bash
python app.py
```

## 目录结构

- `/static/images/` - 存放图片文件
- `/static/texts/` - 存放对应的文本文件
- `/templates/` - 存放 HTML 模板
- `app.py` - 主应用程序
- `requirements.txt` - 项目依赖 