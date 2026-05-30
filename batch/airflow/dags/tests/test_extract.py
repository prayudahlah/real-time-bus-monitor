from unittest.mock import MagicMock
from tasks.extract import main


def test_extract(mocker):
    resp = MagicMock(
        headers={"content-length": "200"},
        iter_content=lambda **_: [b"x" * 200],
    )
    mocker.patch("tasks.extract.requests.get", return_value=resp)

    client = MagicMock()
    mocker.patch("tasks.extract.get_minio_client", return_value=client)

    mock_zip = MagicMock()
    mock_zip.namelist.return_value = [
        "routes.txt",
        "stops.txt",
        "trips.txt",
        "stop_times.txt",
    ]
    mock_zip.open.return_value = MagicMock()

    zip_ctx = MagicMock()
    zip_ctx.__enter__.return_value = mock_zip
    mocker.patch("tasks.extract.zipfile.ZipFile", return_value=zip_ctx)

    df = MagicMock()
    mocker.patch("tasks.extract.pl.read_csv", return_value=df)

    ti = MagicMock()
    run_id = main(ti=ti)

    assert run_id.startswith("run_")
    assert client.put_object.call_count == 5
