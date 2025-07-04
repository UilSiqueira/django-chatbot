# 🌐 README (English & Português)

📄 This document is available in both **English** and **Português**.

- 🇺🇸 [English version](#introduction)
- 🇧🇷 [Versão em Português](#introdução)


# Introduction

The goal of this project is to build a web API using Django Rest Framework that receives conversation and message events (webhooks), stores them in a PostgreSQL database, and processes messages asynchronously with Celery (using Redis as a broker). Based on this processing, the system should generate response messages ("OUTBOUND") that will be displayed when the user queries the conversation via an endpoint.

---

### Project Installation
See the INSTRUCTIONS.md file for setup and usage instructions.

---

# 📌 Requirements

1. **Create two main models in Django:**
   - Conversation
   - Message (related to Conversation)

2. **Main endpoint:**
   - POST `/webhook/`
   - Receives JSON events (described below)
   - Validates payloads and returns appropriate HTTP codes

3. **Query endpoint:**
   - GET `/conversations/{id}/`
   - Returns conversation details:
     - `id`, `status`, `created_at`, `updated_at`
     - List of associated messages (fields: `id`, `type`, `content`, `timestamp`)

4. **Database**
   - PostgreSQL (running in a Docker container)

5. **Broker/Cache for Celery:**
   - Redis (running in a Docker container)

6. **Asynchronous processing:**
   - Celery running message processing tasks

7. **Docker & Docker Compose:**
   - The project must include a docker-compose.yml orchestrating the following services:
     - Django (gunicorn + django)
     - Celery (worker)
     - PostgreSQL
     - Redis

---

# 📦 Webhook Payload Format

The API will receive events via POST to /webhook/, with JSON in the following formats:

## 1. NEW_CONVERSATION
Creates a new conversation (initial state: `OPEN`).

```json
{
  "type": "NEW_CONVERSATION",
  "timestamp": "2025-06-04T14:20:00Z",
  "data": {
    "id": "6a41b347-8d80-4ce9-84ba-7af66f369f6a"
  }
}
```

## 2. NEW_MESSAGE
New message sent by a user (always `type`: `USER`).

```json
{
  "type": "NEW_MESSAGE",
  "timestamp": "2025-06-04T14:20:05Z",
  "data": {
    "id": "49108c71-4dca-4af3-9f32-61bc745926e2",
    "content": "Hi, I'd like information about renting an apartment.",
    "conversation_id": "6a41b347-8d80-4ce9-84ba-7af66f369f6a"
  }
}
```

## 3. CLOSE_CONVERSATION
Closes the conversation (status becomes CLOSED).

```json
{
  "type": "CLOSE_CONVERSATION",
  "timestamp": "2025-06-04T14:25:00Z",
  "data": {
    "id": "6a41b347-8d80-4ce9-84ba-7af66f369f6a"
  }
}
```

---

# 📌 Business Rules

## 1. Conversation States
- On creation, status = OPEN.
- Once closed, status = CLOSED; closed conversations do not accept new messages (NEW_MESSAGE should return HTTP 400).

## 2. Messages (Message)
- **Allowed types:**
  - "INBOUND":  messages received by the API/Webhook (payload)
  - "OUTBOUND": messages generated internally by the application
- **Each Message must have:**
  - id (UUID) – unique
  - conversation_id (FK)
  - type: "INBOUND" ou "OUTBOUND"
  - content (text)
  - timestamp (event DateTime)
  - additional fields if necessary

## 3. Endpoint Responses
- Invalid payloads (wrong format, business rules violated) must return `HTTP 400 Bad Request`
- Valid message payloads must return `HTTP 202 Accepted` and start asynchronous processing via a Celery task
- Expected returns:
  - **NEW_CONVERSATION:**
    - 201 Created (success)
    - 400 Bad Request (if ID already exists)
  - **NEW_MESSAGE:**
    - 202 Accepted (if valid payload, async process scheduled or buffered)
    - 400 Bad Request (if conversation is closed, payload is invalid, or buffer expired)
  - **CLOSE_CONVERSATION:**
    - 200 OK (success)
    - 400 Bad Request (if conversation does not exist or is already closed)
  - **GET /conversations/{id}:**
    - 200 OK (success, returns conversation JSON)
    - 404 Not Found (not found)


## 4. Out-of-Order Messages
- The application must tolerate slight delays in receiving webhook events.
  - Example: a NEW_MESSAGE that references a Conversation not yet created because the NEW_CONVERSATION has not arrived yet
  - Tolerance limit: 6 seconds

**Timing example:**
- T=0s: NEW_MESSAGE (`id=abc`) arrives for `conversation_id=123`
- T=2s: NEW_CONVERSATION with `id=123` (within 6s limit)
- T=7s: NEW_MESSAGE (`id=dce`) arrives for `conversation_id=456`
- T=15s: NEW_CONVERSATION with `id=456`

- In this case, message with id `abc` should be included in conversation with id `123` and processed normally. However, the message with id `dce` is invalid and should not be processed, as it exceeded the maximum tolerance period of 6s.

## 5. User Multi-Message Grouping
- In real scenarios, humans may split communication into several messages.

- **Example flow**:
  - T=0s: "Hi!"
  - T=2s: "I'm looking for a house"
  - T=4s: "With 2 bedrooms!"

- The application must ensure that a single message from a user is processed normally.
- However, if multiple messages arrive within a short time span (max 5s between them), they should be grouped and processed together as a single `OUTBOUND` message.

In summary:
- A single message: processed normally.
- Multiple messages within 5s intervals: grouped into one asynchronous job, generating only one response.

- **Example flow:**
  1. T=0s: "Hi" arrives
  2. T=2s: "How are you?" arrives
  3. T=5s: "I'd like to rent a property" arrives
  4. If no new message arrives before T=10s, group all 3 messages into one response.

## 6. Response Generation

Message processing handled by Celery must **automatically generate a new `OUTBOUND` message**, stored in the database and linked to the same conversation as the received messages.

The `OUTBOUND` content should be a **standard message listing the IDs of received messages** in the grouping. Format:

```python
"""Received messages:\n{id-1}\n{id-2}"""
```

### Examples

**Case 1 – Single message**

If the app receives a single INBOUND message within the 5s window with `id`:
- 55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1

The generated `OUTBOUND` message must contain:
```python
"""Received messages:
55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1
"""
```

**Case 2 – Multiple grouped messages**

If the app receives three INBOUND messages quickly (≤ 5s between each), with the following `ids`:
- 55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1  
- 8d41e347-da5f-4d03-8377-4378d86cfcf0  
- 1f9e918a-6d32-4a75-93a7-34b9e0faff22  

The generated `OUTBOUND` message must contain:

```python
"""Received messages:
55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1
8d41e347-da5f-4d03-8377-4378d86cfcf0
1f9e918a-6d32-4a75-93a7-34b9e0faff22
"""
```

## 7. Conversation Closure
- The CLOSE_CONVERSATION event sets status = CLOSED.

---

# 🚀 Technologies and Tools

## Language/Framework:
- Python 3.10+
- Django
- Django Rest Framework

## Asynchronous Processing:
- Celery
- Redis (as broker and/or result backend)

## Database:
- PostgreSQL

## Containerization:
- Docker
- docker-compose

### Prerequisites

- Docker and Docker Compose installed
- Git

# 📚 References

- [Django Rest Framework](https://www.django-rest-framework.org/)
- [Django](https://www.djangoproject.com/)
- [Celery](https://docs.celeryproject.org/)
- [Redis](https://redis.io/)

---

# Introdução

O objetivo deste projeto é a criação de uma web API utilizando Django Rest Framework que receba eventos de conversa e mensagem (webhooks), armazene-os em um banco PostgreSQL, processe mensagens de forma assíncrona com Celery (usando Redis como broker). A partir desse processamento, o sistema deve gerar mensagens de resposta ("OUTBOUND") que serão exibidas quando o usuário consultar a conversa, via endpoint.

---

### Instalação do Projeto
Acesse o arquivo INSTRUCTIONS.md com as instruções para rodar o projeto.

---

# 📌 Requisitos

1. **Criar dois modelos principais no Django:**
   - Conversation
   - Message (relacionado a Conversation)

2. **Endpoint principal:**
   - POST `/webhook/`
   - Recebe eventos JSON (descritos abaixo)
   - Valida payloads e retorna códigos HTTP apropriados

3. **Endpoint de consulta:**
   - GET `/conversations/{id}/`
   - Retorna detalhes da conversa:
     - `id`, `status`, `created_at`, `updated_at`
     - Lista de mensagens associadas (campos: `id`, `type`, `content`, `timestamp`)

4. **Banco de dados:**
   - PostgreSQL (rodando em container Docker)

5. **Broker/Cache para Celery:**
   - Redis (rodando em container Docker)

6. **Processamento assíncrono:**
   - Celery executando tasks de processamento de mensagens

7. **Docker & Docker Compose:**
   - O projeto deve incluir docker-compose.yml orquestrando os seguintes serviços:
     - Django (gunicorn + django)
     - Celery (worker)
     - PostgreSQL
     - Redis

---

# 📦 Formato dos Webhooks

A API receberá eventos via POST em /webhook/, com JSON nos formatos:

## 1. NEW_CONVERSATION
Cria uma nova conversa (estado inicial: `OPEN`).

```json
{
  "type": "NEW_CONVERSATION",
  "timestamp": "2025-06-04T14:20:00Z",
  "data": {
    "id": "6a41b347-8d80-4ce9-84ba-7af66f369f6a"
  }
}
```

## 2. NEW_MESSAGE
Nova mensagem enviada por usuário (sempre `type`: `USER`).

```json
{
  "type": "NEW_MESSAGE",
  "timestamp": "2025-06-04T14:20:05Z",
  "data": {
    "id": "49108c71-4dca-4af3-9f32-61bc745926e2",
    "content": "Olá, quero informações sobre alugar um apartamento.",
    "conversation_id": "6a41b347-8d80-4ce9-84ba-7af66f369f6a"
  }
}
```

## 3. CLOSE_CONVERSATION
Fecha a conversa (estado passa a CLOSED).

```json
{
  "type": "CLOSE_CONVERSATION",
  "timestamp": "2025-06-04T14:25:00Z",
  "data": {
    "id": "6a41b347-8d80-4ce9-84ba-7af66f369f6a"
  }
}
```

---

# 📌 Regras de Negócio

## 1. Estados de Conversation
- Ao criar, status = OPEN.
- Depois de fechado, status = CLOSED; conversas fechadas não aceitam novas mensagens (NEW_MESSAGE retorna HTTP 400).

## 2. Mensagens (Message)
- **Tipos permitidos:**
  - "INBOUND": mensagens recebidas pela API/Webhook (payload)
  - "OUTBOUND": gerado internamente pela aplicação
- **Cada Message tem:**
  - id (UUID) – único
  - conversation_id (FK)
  - type: "INBOUND" ou "OUTBOUND"
  - content (texto)
  - timestamp (DateTime do evento)
  - campos adicionais a seu critério, se achar necessário.

## 3. Retorno dos endpoints
- Payloads inválidos (formato incorreto, regras de negócio violadas) devem retornar `HTTP 400 Bad Request`
- Payloads de mensagem válidos devem retornar `HTTP 202 Accepted` e iniciar o processamento assíncrono via Celery task
- Retornos esperados:
  - **NEW_CONVERSATION:**
    - 201 Created (sucesso)
    - 400 Bad Request (se ID já existir)
  - **NEW_MESSAGE:**
    - 202 Accepted (se payload válido, processo assíncrono agendado ou bufferizado)
    - 400 Bad Request (se conversa fechada, payload inválido ou buffer expirado)
  - **CLOSE_CONVERSATION:**
    - 200 OK (sucesso)
    - 400 Bad Request (se conversa não existir ou já fechada)
  - **GET /conversations/{id}:**
    - 200 OK (sucesso, retorna JSON da conversa)
    - 404 Not Found (não existe)


## 4. Mensagens fora de ordem
- A aplicação deve tolerar uma breve falta de sincronia no recebimento de webhooks
  - Por exemplo, uma NEW_MESSAGE que faz referência a uma `Conversation` que ainda não foi criada, pois o NEW_CONVERSATION ainda não chegou
  - O limite deve ser de, no máximo, 6 segundos

**Exemplo de tempos:**
- T=0s: Chega NEW_MESSAGE (`id=abc`) para `conversation_id=123`
- T=2s: Chega NEW_CONVERSATION com `id=123` (dentro do limite de 6s)
- T=7s: Chega NEW_MESSAGE (`id=dce`) para `conversation_id=456`
- T=15s: Chega NEW_CONVERSATION com `id=456`

- Neste cenário, a mensagem com id `abc` deverá ser incluída na conversa com id `123` e ser processada normalmente. Porém, a mensagem com id `dce` é inválida e não deveria ser processada, pois ultrapassou o período limite de tolerância de 6s.

## 5. Processamento de múltiplas mensagens do usuário
- Na vida real, seres humanos podem "quebrar" a sua comunicação em várias mensagens

- **Exemplo de fluxo**:
  - T=0s: "Oi!"
  - T=2s: "Estou buscando uma casa"
  - T=4s: "Com 2 quartos para morar!"

- A aplicação deve garantir que se um usuário enviar apenas UMA mensagem, ela será processada normalmente.
- Porém, caso o usuário envie várias mensagens em sequência rápida (intervalo de até 5 segundos entre elas), essas mensagens devem ser agrupadas e processadas juntamente, gerando apenas uma mensagem (type `OUTBOUND`).

Ou seja:
- Quando um usuário enviar UMA mensagem, deve ser processada sozinha.
- Se o usuário enviar várias mensagens em sequência rápida (intervalo de até 5 segundos entre elas), essas mensagens devem ser agrupadas em um único job assíncrono, evitando múltiplas respostas redundantes.

- **Exemplo de fluxo:**
  1. T=0s: chega "Oi"
  2. T=2s: chega "Tudo bem?"
  3. T=5s: chega "Quero alugar imóvel."
  4. Se nenhuma mensagem nova chegar antes de T=10s, processe as três juntas e gere uma resposta única.

## 6. Geração de Resposta

O processamento de mensagens realizado pelo Celery deve **gerar automaticamente uma nova mensagem do tipo `OUTBOUND`**, que será armazenada no banco de dados e vinculada à mesma conversa das mensagens recebidas.

A resposta `OUTBOUND` deve conter um **conteúdo (`content`) padrão que lista os IDs das mensagens recebidas** no agrupamento. O conteúdo deve seguir o seguinte formato:

```python
"""Mensagens recebidas:\n{id-1}\n{id-2}"""
```

### Exemplos

**Caso 1 – Mensagem única**

Se a aplicação receber uma única mensagem INBOUND no período de 5s com o `id`:
- 55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1

A mensagem `OUTBOUND` gerada deverá ter o seguinte conteúdo:
```python
"""Mensagens recebidas:
55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1
"""
```

**Caso 2 – Múltiplas mensagens agrupadas**

Se a aplicação receber três mensagens INBOUND em sequência rápida (com até 5 segundos entre cada uma), com os seguintes `ids`:
- 55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1  
- 8d41e347-da5f-4d03-8377-4378d86cfcf0  
- 1f9e918a-6d32-4a75-93a7-34b9e0faff22  

A mensagem `OUTBOUND` gerada deverá ter o seguinte conteúdo:

```python
"""Mensagens recebidas:
55ebb68a-a8ef-47d4-9a28-c97e0f0ec8f1
8d41e347-da5f-4d03-8377-4378d86cfcf0
1f9e918a-6d32-4a75-93a7-34b9e0faff22
"""
```

## 7. Fechamento de Conversa
- O evento CLOSE_CONVERSATION marca status = CLOSED.

---

# 🚀 Tecnologias e Ferramentas

## Linguagem/Framework:
- Python 3.10+
- Django
- Django Rest Framework

## Processamento Assíncrono:
- Celery
- Redis (broker e/ou backend de resultados)

## Banco de Dados:
- PostgreSQL

## Containerização:
- Docker
- docker-compose

### Pré-requisitos

- Docker e Docker Compose instalados
- Git

# 📚 Referências

- [Django Rest Framework](https://www.django-rest-framework.org/)
- [Django](https://www.djangoproject.com/)
- [Celery](https://docs.celeryproject.org/)
- [Redis](https://redis.io/)
