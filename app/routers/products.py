import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import DATA_DIR, get_db
from app.generation.garment_focus import GARMENT_TYPE_LABELS
from app.models import FetchStatus, Product, ProductImage
from app.schemas import ProductImageOut, ProductOut
from app.scraping.download import ALLOWED_IMAGE_TYPES, download_image
from app.scraping.fetch import build_failure_message, fetch_product

router = APIRouter()

UPLOADS_DIR = DATA_DIR / "uploads" / "products"

ALLOWED_GARMENT_TYPES = set(GARMENT_TYPE_LABELS) | {""}


def product_to_out(product: Product) -> ProductOut:
    def img_out(img: ProductImage) -> ProductImageOut:
        return ProductImageOut(
            id=img.id,
            url=f"/uploads/products/{img.file_path}",
            source_url=img.source_url or "",
            original_filename=img.original_filename or "",
        )

    return ProductOut(
        id=product.id,
        name=product.name,
        source_url=product.source_url or "",
        fetch_method_used=product.fetch_method_used or "",
        fetch_status=product.fetch_status,
        fetch_error=product.fetch_error or "",
        description=product.description or "",
        additional_context=product.additional_context or "",
        garment_type=product.garment_type or "",
        created_at=product.created_at,
        updated_at=product.updated_at,
        images=[img_out(i) for i in product.images],
    )


def save_manual_upload(product_id: str, upload: UploadFile) -> ProductImage:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Unsupported image type: {upload.content_type}")
    ext = ALLOWED_IMAGE_TYPES[upload.content_type]
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_dir = UPLOADS_DIR / product_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    with dest_path.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return ProductImage(
        product_id=product_id,
        file_path=f"{product_id}/{filename}",
        original_filename=upload.filename or "",
    )


@router.get("", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).order_by(Product.created_at.desc()).all()
    return [product_to_out(p) for p in products]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product_to_out(product)


@router.post("", response_model=ProductOut)
def create_product(
    source_url: str = Form(""),
    garment_type: str = Form(""),
    manual_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    source_url = source_url.strip()
    manual_files = [f for f in manual_images if f.filename]

    if not source_url and not manual_files:
        raise HTTPException(400, "Provide a product URL or upload product images")
    if garment_type not in ALLOWED_GARMENT_TYPES:
        raise HTTPException(400, f"garment_type must be one of {sorted(ALLOWED_GARMENT_TYPES)}")

    product = Product(
        name=source_url or "New product",
        source_url=source_url,
        fetch_status=FetchStatus.failed,
        garment_type=garment_type,
    )
    db.add(product)
    db.flush()  # assign product.id

    scraped_images: list[str] = []
    title, description, method_used, url_fetch_error = "", "", "", ""

    if source_url:
        result, attempts = fetch_product(source_url)
        if result:
            scraped_images = result.images
            title, description, method_used = result.title, result.description, result.method
        else:
            url_fetch_error = build_failure_message(source_url, attempts)

    downloaded_any = False
    if scraped_images:
        dest_dir = UPLOADS_DIR / product.id
        for img_url in scraped_images:
            try:
                saved_path = download_image(dest_dir, img_url)
            except Exception:  # noqa: BLE001 — any single image failing shouldn't abort the product
                continue
            rel_path = f"{product.id}/{saved_path.name}"
            db.add(ProductImage(product_id=product.id, file_path=rel_path, source_url=img_url))
            downloaded_any = True

        if downloaded_any:
            product.fetch_status = FetchStatus.success
            product.fetch_method_used = method_used
            product.name = title or source_url
            product.description = description
        else:
            url_fetch_error = (
                url_fetch_error
                or f"Found {len(scraped_images)} image link(s) on the page via {method_used}, "
                "but couldn't download any of them."
            )

    if product.fetch_status != FetchStatus.success:
        if manual_files:
            for f in manual_files:
                db.add(save_manual_upload(product.id, f))
            product.fetch_status = FetchStatus.success
            product.fetch_method_used = "manual_upload"
            if source_url:
                product.fetch_error = f"{url_fetch_error} Used manually uploaded photos instead."
        else:
            product.fetch_status = FetchStatus.failed
            product.fetch_error = url_fetch_error or "No product URL or images were provided."

    db.commit()
    db.refresh(product)
    return product_to_out(product)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    name: str = Form(...),
    additional_context: str = Form(""),
    garment_type: str = Form(""),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    name = name.strip()
    if not name:
        raise HTTPException(400, "Name is required")
    if garment_type not in ALLOWED_GARMENT_TYPES:
        raise HTTPException(400, f"garment_type must be one of {sorted(ALLOWED_GARMENT_TYPES)}")

    product.name = name
    product.additional_context = additional_context
    product.garment_type = garment_type
    db.commit()
    db.refresh(product)
    return product_to_out(product)


@router.post("/{product_id}/images", response_model=ProductOut)
def add_product_images(
    product_id: str,
    images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    files = [f for f in images if f.filename]
    if not files:
        raise HTTPException(400, "No images provided")

    for f in files:
        db.add(save_manual_upload(product.id, f))
    if product.fetch_status != FetchStatus.success:
        product.fetch_status = FetchStatus.success
        product.fetch_method_used = product.fetch_method_used or "manual_upload"

    db.commit()
    db.refresh(product)
    return product_to_out(product)


@router.delete("/{product_id}/images/{image_id}", response_model=ProductOut)
def delete_product_image(product_id: str, image_id: str, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    image = next((i for i in product.images if i.id == image_id), None)
    if not image:
        raise HTTPException(404, "Image not found")
    if len(product.images) <= 1:
        raise HTTPException(400, "Product must keep at least one photo")

    abs_path = UPLOADS_DIR / image.file_path
    if abs_path.exists():
        abs_path.unlink()
    db.delete(image)
    db.commit()
    db.refresh(product)
    return product_to_out(product)


@router.delete("/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    product_dir = UPLOADS_DIR / product.id
    db.delete(product)
    db.commit()
    if product_dir.exists():
        shutil.rmtree(product_dir, ignore_errors=True)
    return {"ok": True}
