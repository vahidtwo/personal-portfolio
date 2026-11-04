# Throwaway stage: resolve the cloned commit from .git/HEAD and its ref (loose or packed) into one file.
# Only HEAD, refs/heads and packed-refs reach the build (.dockerignore); anything else, or no .git, gives "unknown".
FROM python:3.12-slim AS git-sha
RUN --mount=type=bind,target=/src sh -eu -c '\
  d=/src/.git; v=""; \
  if [ -f "$d/HEAD" ]; then \
    h=$(head -n 1 "$d/HEAD"); \
    case "$h" in \
      "ref: refs/heads/"*) r=${h#ref: }; \
        case "$r" in *..*) r="";; esac; \
        if [ -n "$r" ] && [ -f "$d/$r" ]; then v=$(head -n 1 "$d/$r"); \
        elif [ -n "$r" ] && [ -f "$d/packed-refs" ]; then v=$(awk -v r="$r" "\$2 == r { print \$1; exit }" "$d/packed-refs"); fi;; \
      "ref: "*) ;; \
      *) v=$h;; \
    esac; \
  fi; \
  mkdir -p /out; \
  if printf "%s" "$v" | grep -Eqx "[0-9a-f]{40}"; then printf "%s\n" "$v" > /out/GIT_SHA; else echo unknown > /out/GIT_SHA; fi; \
  echo "git-sha: $(cat /out/GIT_SHA)"'

FROM python:3.12-slim

WORKDIR /app
# Deployed commit for /health: build-info/GIT_SHA from the git-sha stage; --build-arg GIT_SHA=<commit> overrides it.
ARG GIT_SHA=
ENV GIT_SHA=$GIT_SHA
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY --from=git-sha /out/GIT_SHA ./build-info/GIT_SHA
RUN mkdir -p /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# One worker so the hourly price/snapshot job does not run twice.
# Trust X-Forwarded-* only from the reverse proxy. Set FORWARDED_ALLOW_IPS in Dokploy to Traefik's
# address or network (e.g. the dokploy-network subnet); until it is set, the old "*" stays (no behavior change).
ENV FORWARDED_ALLOW_IPS="*"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
