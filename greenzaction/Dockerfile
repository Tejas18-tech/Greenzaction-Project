FROM node:22-alpine AS frontend
WORKDIR /app
COPY package.json vite.config.js index.html ./
COPY src ./src
COPY public ./public
RUN npm install && npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=3000
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY .env.example ./
COPY --from=frontend /app/dist ./dist
EXPOSE 3000
CMD ["sh", "-c", "PORT=${PORT:-3000} python3 -m backend.app"]
