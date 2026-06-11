FROM public.ecr.aws/lambda/python:3.12

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy function code
COPY handler.py feature_functions.py store_writer.py ./

# Lambda handler entrypoint
CMD ["handler.lambda_handler"]
