FROM node:24-bookworm-slim
ARG BUILD_ARCH
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-yaml python3-flask ca-certificates curl unzip lua5.3 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @smartthings/cli@3.0.1 && smartthings --version
RUN mkdir -p /opt/st && curl --fail --location --retry 3 https://codeload.github.com/cleverk2000-code/ST/zip/9935b5d059c89e3be3e6f2ace7f63d3de07d0cce -o /tmp/st.zip && unzip -q /tmp/st.zip -d /tmp/st-src && cp -a /tmp/st-src/ST-9935b5d059c89e3be3e6f2ace7f63d3de07d0cce/direct /tmp/st-src/ST-9935b5d059c89e3be3e6f2ace7f63d3de07d0cce/universal /opt/st/ && rm -rf /tmp/st.zip /tmp/st-src
COPY manager.py /opt/manager.py
COPY webapp.py /opt/webapp.py
WORKDIR /opt
EXPOSE 8099
CMD ["python3","/opt/webapp.py"]
