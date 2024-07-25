# 使用官方的Python基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 将requirements.txt复制到工作目录
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录的内容复制到工作目录
COPY . .

# 暴露Flask应用程序运行的端口
EXPOSE 5050

# 运行入口点脚本
CMD ["python", "donate.py"]
