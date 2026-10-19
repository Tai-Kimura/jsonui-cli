import os

import boto3
import psycopg
import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
queue = boto3.client("sqs")
bucket = os.environ["UPLOADS_S3_BUCKET"]
conn = psycopg.connect(os.getenv("DATABASE_URL"))
mystery = os.getenv("WEIRD_SERVICE_URL")
