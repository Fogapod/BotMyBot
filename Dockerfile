FROM python:3.7-slim

# enables proper stdout flushing
ENV PYTHONUNBUFFERED=yes

# pip optimizations
ENV PIP_NO_CACHE_DIR=yes
ENV PIP_DISABLE_PIP_VERSION_CHECK=yes

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# espeak-ng for tts command
RUN espeak_deps='gcc make autoconf automake libtool pkg-config libsonic-dev' && \
    apt-get update && apt-get install -y --no-install-recommends $espeak_deps && \
    rm -rf /var/lib/apt/lists/* && \
    git clone https://github.com/espeak-ng/espeak-ng.git --depth=1 && cd espeak-ng && \
    ./autogen.sh && \
    ./configure --with-extdict-ru && \
    make && \
    cd .. && rm -rf espeak-ng && \
    apt-get purge -y --auto-remove $espeak_deps


# chromium for screenshot command
RUN arsenic_deps='unzip wget' && \
    apt-get update && apt-get install -y --no-install-recommends $arsenic_deps && \
    apt-get update && apt-get install -y --no-install-recommends chromium && \
    rm -rf /var/lib/apt/lists/* && \
    wget -O chromedriver.zip https://chromedriver.storage.googleapis.com/79.0.3945.36/chromedriver_linux64.zip && \
    unzip chromedriver.zip && \
    chmod +x chromedriver && \
    mv chromedriver /usr/local/bin && \
    rm -f chromedriver.zip && \
    apt-get purge -y --auto-remove $arsenic_deps

COPY requirements.txt .

RUN pip_deps='gcc make' && \
    apt-get update && apt-get install -y --no-install-recommends $pip_deps && \
    rm -rf /var/lib/apt/lists/* && \
    pip install -Ur requirements.txt && \
    apt-get purge -y --auto-remove $pip_deps

COPY . .

RUN addgroup kiwi && \
    useradd -g kiwi kiwi && \
    chown -R kiwi:kiwi /code

USER kiwi

ENTRYPOINT ["./run.sh"]
