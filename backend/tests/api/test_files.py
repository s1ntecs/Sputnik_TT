from io import BytesIO


async def test_create_and_list_file(client):
    resp = await client.post(
        "/files",
        data={"title": "hello"},
        files={"file": ("hello.txt", BytesIO(b"hi"), "text/plain")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "hello"
    assert body["size"] == 2
    assert body["processing_status"] == "uploaded"

    listing = await client.get("/files")
    assert listing.status_code == 200
    assert any(item["id"] == body["id"] for item in listing.json())


async def test_empty_file_rejected(client):
    resp = await client.post(
        "/files",
        data={"title": "empty"},
        files={"file": ("empty.txt", BytesIO(b""), "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "File is empty"


async def test_update_file_title(client):
    up = await client.post(
        "/files",
        data={"title": "old"},
        files={"file": ("a.txt", BytesIO(b"x"), "text/plain")},
    )
    file_id = up.json()["id"]

    resp = await client.patch(f"/files/{file_id}", json={"title": "new"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "new"


async def test_update_rejects_empty_title(client):
    up = await client.post(
        "/files",
        data={"title": "t"},
        files={"file": ("a.txt", BytesIO(b"x"), "text/plain")},
    )
    file_id = up.json()["id"]

    resp = await client.patch(f"/files/{file_id}", json={"title": ""})
    assert resp.status_code == 422


async def test_create_rejects_empty_title_symmetric_with_patch(client):
    resp = await client.post(
        "/files",
        data={"title": ""},
        files={"file": ("a.txt", BytesIO(b"x"), "text/plain")},
    )
    assert resp.status_code == 422


async def test_download_cyrillic_filename_header(client):
    up = await client.post(
        "/files",
        data={"title": "title"},
        files={"file": ("привет.txt", BytesIO(b"hi"), "text/plain")},
    )
    file_id = up.json()["id"]

    resp = await client.get(f"/files/{file_id}/download")
    assert resp.status_code == 200

    cd = resp.headers.get("content-disposition", "")
    assert "filename*=UTF-8''" in cd
    assert "%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82" in cd
