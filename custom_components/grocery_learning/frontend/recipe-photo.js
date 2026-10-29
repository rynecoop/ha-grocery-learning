// Original phone photos stay on the device. Only the prepared raster is sent
// to HA; keep its cap identical to recipe_images.MAX_OUTPUT on the server.
const { dataUrlByteLength } = await import(`./state-helpers.js${new URL(import.meta.url).search}`);
export const RECIPE_PHOTO_MAX_BYTES = 256 * 1024;
const MAX_ORIGINAL_BYTES = 100 * 1024 * 1024;
const PHOTO_TYPES = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif", "image/avif"]);

async function decodePhoto(file, isCurrent) {
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      return { source: bitmap, width: bitmap.width, height: bitmap.height, release: () => bitmap.close() };
    } catch (_) {
      // Some browsers can display a phone photo (including HEIC on Safari)
      // even when their ImageBitmap decoder cannot read that same file.
      if (!isCurrent()) return null;
    }
  }
  const url = URL.createObjectURL(file);
  const img = new Image();
  try {
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = () => reject(new Error("This browser couldn’t read that photo format. Choose a JPEG, PNG or WebP photo, or open HEIC photos on a supported device."));
      img.src = url;
    });
    return { source: img, width: img.naturalWidth, height: img.naturalHeight,
      release: () => { img.src = ""; URL.revokeObjectURL(url); } };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

export async function prepareRecipePhoto(file, isCurrent = () => true) {
  const type = String(file.type || "").toLowerCase();
  // iOS photo providers sometimes omit MIME information. A recognized raster
  // extension may identify those files; decoding still validates the content.
  const namedPhoto = /\.(?:jpe?g|png|webp|heic|heif|avif)$/i.test(file.name || "");
  if (!PHOTO_TYPES.has(type) && !((!type || type === "application/octet-stream") && namedPhoto)) {
    throw new Error("Choose a photo from your library (JPEG, PNG, WebP, HEIC or AVIF).");
  }
  if (!file.size || file.size > MAX_ORIGINAL_BYTES) throw new Error("Choose a photo under 100 MB.");
  let decoded;
  const canvas = document.createElement("canvas");
  try {
    decoded = await decodePhoto(file, isCurrent);
    if (!decoded || !isCurrent()) return null;
    const { width, height, source } = decoded;
    if (!(width > 0 && height > 0)) throw new Error("That photo could not be read. Try selecting it again.");
    // Keep aspect ratio and orientation. If a detailed photo cannot fit at
    // 1200px, shrink it automatically rather than asking the user to edit it.
    for (let edge = Math.min(1200, Math.max(width, height));; edge = Math.max(1, Math.floor(edge * 0.75))) {
      if (!isCurrent()) return null;
      const scale = Math.min(1, edge / Math.max(width, height));
      canvas.width = Math.max(1, Math.round(width * scale));
      canvas.height = Math.max(1, Math.round(height * scale));
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Photo preparation is unavailable. Try reopening the app.");
      // Photo transparency gets a neutral background, including JPEG fallback.
      ctx.fillStyle = "white";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
      for (const quality of [0.8, 0.65, 0.45]) {
        let data = canvas.toDataURL("image/webp", quality);
        // Browsers without WebP encoding silently return PNG. JPEG provides
        // predictable lossy compression there without asking users to convert.
        if (!data.startsWith("data:image/webp;base64,")) data = canvas.toDataURL("image/jpeg", quality);
        if (/^data:image\/(?:webp|jpeg);base64,/.test(data) && dataUrlByteLength(data) > 0 && dataUrlByteLength(data) <= RECIPE_PHOTO_MAX_BYTES) return data;
      }
      if (edge === 1) throw new Error("That photo could not be prepared. Try selecting it again.");
    }
  } finally {
    decoded?.release();
    canvas.width = canvas.height = 1;
  }
}
