import boto3
import gzip
import json
import os
import base64
import time

# Clients initialized once for reuse
kinesis_client = boto3.client("kinesis")
logs_client = boto3.client("logs")
s3_client = boto3.client("s3")

# Configuration from environment
s3_bucket_name = os.getenv("S3_BUCKET_NAME", "arcxpplogs")
log_group_name = "ArcXP/DynamicLogStreams"
stream_tokens = {}
max_log_buffer_size = 100

def ensure_log_group():
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass

def ensure_log_stream(log_stream_name):
    if log_stream_name not in stream_tokens:
        try:
            logs_client.create_log_stream(
                logGroupName=log_group_name,
                logStreamName=log_stream_name
            )
            stream_tokens[log_stream_name] = None
        except logs_client.exceptions.ResourceAlreadyExistsException:
            response = logs_client.describe_log_streams(
                logGroupName=log_group_name,
                logStreamNamePrefix=log_stream_name
            )
            if response["logStreams"]:
                token = response["logStreams"][0].get("uploadSequenceToken")
                stream_tokens[log_stream_name] = token

def send_to_cloudwatch_log(message, timestamp, log_stream_name):
    ensure_log_stream(log_stream_name)
    token = stream_tokens.get(log_stream_name)

    log_event = {
        'logGroupName': log_group_name,
        'logStreamName': log_stream_name,
        'logEvents': [{'timestamp': timestamp, 'message': message}]
    }
    if token:
        log_event['sequenceToken'] = token

    response = logs_client.put_log_events(**log_event)
    stream_tokens[log_stream_name] = response['nextSequenceToken']

def upload_to_s3(log_buffer, log_stream_name):
    if not log_buffer:
        return

    s3_key = f"{log_stream_name}/{time.strftime('%Y-%m-%d')}.log"
    log_data = "\n".join(log_buffer)

    s3_client.put_object(
        Bucket=s3_bucket_name,
        Key=s3_key,
        Body=log_data
    )

def handler(event, context):
    ensure_log_group()
    log_buffer = []

    for record in event['Records']:
        try:
            # Decode and decompress
            compressed_payload = base64.b64decode(record['kinesis']['data'])
            decompressed = gzip.decompress(compressed_payload)
            payload = json.loads(decompressed)

            log_stream_name = payload.get("logGroup", "unknown-source").replace("/", "_")

            for event_log in payload.get("logEvents", []):
                message = event_log.get("message", "")
                timestamp = int(event_log.get("timestamp", time.time() * 1000))

                print(f"[{log_stream_name}] Forwarding: {message.strip()}")
                send_to_cloudwatch_log(message.strip(), timestamp, log_stream_name)
                log_buffer.append(message.strip())

                if len(log_buffer) >= max_log_buffer_size:
                    upload_to_s3(log_buffer, log_stream_name)
                    log_buffer.clear()

        except Exception as e:
            print("Error processing record:", e)

    if log_buffer:
        upload_to_s3(log_buffer, log_stream_name)

    return {
        'statusCode': 200,
        'body': 'Processed records and forwarded to CloudWatch Logs + S3.'
    }
