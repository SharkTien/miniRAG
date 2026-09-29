import boto3
from botocore.client import Config
from app.config.settings import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET

class StorageManager:
    """Provide the storagemanager application component."""
    def __init__(self, endpoint=MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, bucket=MINIO_BUCKET):
        self.bucket = bucket
        self.client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version='s3v4')
        )

    def init_storage(self):
        """Initialize storage."""
        try:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except Exception:
                self.client.create_bucket(Bucket=self.bucket)
                print(f"Bucket {self.bucket} created")
        except Exception as e:
            print(f"Error initializing MinIO: {e}")

    def upload_fileobj(self, file_obj, object_key, content_type):
        """Upload fileobj."""
        self.client.upload_fileobj(
            file_obj,
            self.bucket,
            object_key,
            ExtraArgs={'ContentType': content_type}
        )

    def download_file(self, object_key, file_path):
        """Run the download file operation."""
        self.client.download_file(self.bucket, object_key, file_path)

    def get_object(self, object_key):
        """Return object."""
        return self.client.get_object(Bucket=self.bucket, Key=object_key)

    def delete_object(self, object_key):
        """Delete object."""
        self.client.delete_object(Bucket=self.bucket, Key=object_key)
