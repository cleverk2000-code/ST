FROM node:24-bookworm-slim
ARG BUILD_ARCH
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-yaml python3-flask ca-certificates curl unzip lua5.3 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @smartthings/cli@3.0.1 && smartthings --version
RUN mkdir -p /opt/st && curl --fail --location --retry 3 https://codeload.github.com/cleverk2000-code/ST/zip/a112378bbd90b2a7ce0c8c69aa6d91c96056125d -o /tmp/st.zip && unzip -q /tmp/st.zip -d /tmp/st-src && cp -a /tmp/st-src/ST-a112378bbd90b2a7ce0c8c69aa6d91c96056125d/direct /tmp/st-src/ST-a112378bbd90b2a7ce0c8c69aa6d91c96056125d/universal /opt/st/ && rm -rf /tmp/st.zip /tmp/st-src
COPY manager.py /opt/manager.py
COPY webapp.py /opt/webapp.py
WORKDIR /opt
EXPOSE 8099
CMD ["python3","/opt/webapp.py"]
