# 一次性验收服务：在 compose 网络内对真实运行的 api/web 执行
# pytest（并发、重启、故障注入）+ Vitest（真实 API 联调）+ Playwright（浏览器重试与错误反馈）。
FROM mcr.microsoft.com/playwright:v1.47.2-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /verify

# Python 侧：API 依赖 + pytest
COPY api/requirements.txt api/requirements-test.txt api/
RUN pip3 install --no-cache-dir -r api/requirements.txt -r api/requirements-test.txt
COPY api/ api/

# Web 侧：Vitest + Playwright 测试依赖（浏览器由基础镜像提供）
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci
COPY web/ web/

COPY verify/run_verify.sh run_verify.sh
RUN chmod +x run_verify.sh

ENV API_ORIGIN=http://api:8000 \
    E2E_BASE_URL=http://web \
    CI=1

CMD ["./run_verify.sh"]
