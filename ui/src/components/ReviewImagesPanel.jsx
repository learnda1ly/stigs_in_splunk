import React, { useCallback, useEffect, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Message from "@splunk/react-ui/Message";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, formatErr } from "../api";
import { Actions } from "../layout";

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || "");
            const comma = result.indexOf(",");
            resolve(comma >= 0 ? result.slice(comma + 1) : result);
        };
        reader.onerror = () => reject(reader.error || new Error("read failed"));
        reader.readAsDataURL(file);
    });
}

function ReviewImageThumb({ reviewId, image, onDelete, canEdit, busy }) {
    const [src, setSrc] = useState("");
    const [loadErr, setLoadErr] = useState("");

    useEffect(() => {
        let cancelled = false;
        setSrc("");
        setLoadErr("");
        apiFetch(`stig_reviews/${reviewId}/images/${image._key}`)
            .then((data) => {
                if (cancelled) {
                    return;
                }
                const b64 = data.content_base64;
                const type = data.content_type || "image/png";
                if (!b64) {
                    setLoadErr("missing image data");
                    return;
                }
                setSrc(`data:${type};base64,${b64}`);
            })
            .catch((err) => {
                if (!cancelled) {
                    setLoadErr(formatErr(err));
                }
            });
        return () => {
            cancelled = true;
        };
    }, [reviewId, image._key, image.content_type]);

    return (
        <div
            style={{
                border: "1px solid var(--border-color, #ccc)",
                borderRadius: 4,
                padding: 8,
                maxWidth: 220,
            }}
        >
            {loadErr ? (
                <Message type="error">{loadErr}</Message>
            ) : src ? (
                <a href={src} target="_blank" rel="noopener noreferrer">
                    <img
                        src={src}
                        alt={image.filename || "review attachment"}
                        style={{ maxWidth: "100%", maxHeight: 160, display: "block" }}
                    />
                </a>
            ) : (
                <WaitSpinner />
            )}
            <div
                style={{
                    fontSize: 12,
                    marginTop: 6,
                    wordBreak: "break-all",
                }}
            >
                {image.filename || image._key}
            </div>
            {canEdit ? (
                <Button
                    appearance="destructive"
                    label="Remove"
                    disabled={busy}
                    onClick={() => onDelete(image._key)}
                />
            ) : null}
        </div>
    );
}

export default function ReviewImagesPanel({ reviewId, editable, onError, onNotice }) {
    const [images, setImages] = useState([]);
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const fileRef = useRef(null);

    const loadImages = useCallback(() => {
        if (!reviewId) {
            setImages([]);
            return;
        }
        setLoading(true);
        apiFetch(`stig_reviews/${reviewId}/images`)
            .then((data) => {
                setImages(data.images || []);
            })
            .catch((err) => {
                setImages([]);
                if (onError) {
                    onError(formatErr(err));
                }
            })
            .finally(() => setLoading(false));
    }, [reviewId, onError]);

    useEffect(() => {
        loadImages();
    }, [loadImages]);

    const onPickFile = () => {
        if (fileRef.current) {
            fileRef.current.click();
        }
    };

    const onFileChange = (event) => {
        const file = event.target.files && event.target.files[0];
        event.target.value = "";
        if (!file || !reviewId) {
            return;
        }
        if (!file.type || !file.type.startsWith("image/")) {
            if (onError) {
                onError("Only image files can be attached.");
            }
            return;
        }
        setBusy(true);
        readFileAsBase64(file)
            .then((content_base64) =>
                apiFetch(`stig_reviews/${reviewId}/images`, {
                    method: "POST",
                    body: {
                        filename: file.name,
                        content_type: file.type,
                        content_base64,
                    },
                })
            )
            .then(() => {
                if (onNotice) {
                    onNotice("Image attached.");
                }
                loadImages();
            })
            .catch((err) => {
                if (onError) {
                    onError(formatErr(err));
                }
            })
            .finally(() => setBusy(false));
    };

    const onDelete = (imageId) => {
        if (!reviewId || !imageId) {
            return;
        }
        setBusy(true);
        apiFetch(`stig_reviews/${reviewId}/images/${imageId}`, { method: "DELETE" })
            .then(() => {
                if (onNotice) {
                    onNotice("Image removed.");
                }
                loadImages();
            })
            .catch((err) => {
                if (onError) {
                    onError(formatErr(err));
                }
            })
            .finally(() => setBusy(false));
    };

    if (!reviewId) {
        return null;
    }

    return (
        <ControlGroup label="Image attachments">
            {editable ? (
                <Actions>
                    <input
                        ref={fileRef}
                        type="file"
                        accept="image/png,image/jpeg,image/gif,image/webp"
                        style={{ display: "none" }}
                        onChange={onFileChange}
                    />
                    <Button
                        appearance="secondary"
                        label="Add image"
                        disabled={busy || loading}
                        onClick={onPickFile}
                    />
                </Actions>
            ) : null}
            {loading ? <WaitSpinner /> : null}
            {!loading && images.length === 0 ? (
                <div style={{ fontSize: 13, opacity: 0.85 }}>No images attached.</div>
            ) : null}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
                {images.map((img) => (
                    <ReviewImageThumb
                        key={img._key}
                        reviewId={reviewId}
                        image={img}
                        canEdit={editable}
                        busy={busy}
                        onDelete={onDelete}
                    />
                ))}
            </div>
        </ControlGroup>
    );
}
