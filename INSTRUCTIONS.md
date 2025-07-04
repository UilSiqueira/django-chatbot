# 🐳 Setup Instructions

Siga os passos abaixo para rodar o projeto localmente usando Docker.

---

## 1. Clone o repositório

```bash
git clone git@github.com:UilSiqueira/django-chatbot.git
cd django-chatbot
```


## 2. Suba os containers

```bash
docker-compose up -d --build
```


## 3. Aplique as migrações

```bash
docker-compose exec web python manage.py migrate
```

## 4. Testar o endpoint
```bash
curl -X POST http://localhost:8000/webhook/ \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "NEW_CONVERSATION",
    "timestamp": "2025-06-04T14:20:00Z",
    "data": {
      "id": "6a41b347-8d80-4ce9-84ba-7af66f369f6a"
    }
  }'
```

✅ Pronto!

Se tudo estiver certo, o backend estará pronto para processar requisições.
