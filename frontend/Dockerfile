FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Hardening del red team (docs/security/red-team-app-2026-09-22.md): sin
# USER, vite corría como root. Reutiliza el usuario "node" ya creado por la
# imagen base node:22-alpine, no hace falta crear uno nuevo.
RUN chown -R node:node /app
USER node

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
