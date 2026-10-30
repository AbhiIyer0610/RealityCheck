from app.ingestion.models import Artifact, ArtifactStatus


def test_create_artifact():
    artifact = Artifact(
        filename="requirements.pdf",
        media_type="application/pdf",
        size_bytes=1024,
    )

    assert artifact.filename == "requirements.pdf"
    assert artifact.media_type == "application/pdf"
    assert artifact.size_bytes == 1024
    assert artifact.status == ArtifactStatus.RECEIVED
    assert artifact.artifact_id is not None
    assert artifact.received_at.tzinfo is not None