FROM public.ecr.aws/lambda/python:3.9

# Install Chrome dependencies
RUN yum install -y \
    wget \
    unzip \
    libX11 \
    libXcomposite \
    libXcursor \
    libXdamage \
    libXext \
    libXi \
    libXtst \
    cups-libs \
    libXScrnSaver \
    libXrandr \
    alsa-lib \
    pango \
    atk \
    at-spi2-atk \
    gtk3 \
    && yum clean all

# Install Chrome
RUN wget -q -O chrome-linux64.zip https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.85/linux64/chrome-linux64.zip \
    && unzip chrome-linux64.zip \
    && mv chrome-linux64 /opt/chrome \
    && chmod +x /opt/chrome/chrome \
    && rm chrome-linux64.zip

# Install ChromeDriver
RUN wget -q -O chromedriver-linux64.zip https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.85/linux64/chromedriver-linux64.zip \
    && unzip chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /opt/chromedriver \
    && chmod +x /opt/chromedriver \
    && rm -rf chromedriver-linux64.zip chromedriver-linux64

# Copy requirements
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install Python packages
RUN pip install -r requirements.txt

# Copy Lambda function and test files
COPY lambda_function.py ${LAMBDA_TASK_ROOT}
COPY test_simple_lambda.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "lambda_function.lambda_handler" ]