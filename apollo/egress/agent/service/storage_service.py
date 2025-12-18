from abc import ABC, abstractmethod
from typing import Union


class BaseStorageService(ABC):
    """
    Storage service class, used to upload results to the storage and generate
    pre-signed URLs for them.
    """

    @abstractmethod
    def write(self, key: str, obj_to_write: Union[bytes, str]):
        """
        Saves the specified contents to the file at `key`.
        """
        pass

    @abstractmethod
    def generate_presigned_url(self, key: str, expiration_seconds: int) -> str:
        """
        Generates a pre-signed URL for the specified key.
        """
        pass


class EmptyStorageService(BaseStorageService):
    def write(self, key: str, obj_to_write: Union[bytes, str]):
        raise NotImplementedError("Not implemented")

    def generate_presigned_url(self, key: str, expiration_seconds: int) -> str:
        raise NotImplementedError("Not implemented")
