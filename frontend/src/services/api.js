const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:4444").replace(/\/$/, "");

export async function processFull(file, fileUrl) {
  const formData = new FormData();

  if (file) {
    formData.append("file", file);
  }

  if (fileUrl && fileUrl.trim() !== "") {
    formData.append("file_url", fileUrl.trim());
  }

  const response = await fetch(`${API_BASE_URL}/api/process`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let errorMessage = "Failed to process file";

    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorMessage;
    } catch {
      // ignore json parse error
    }

    throw new Error(errorMessage);
  }

  return await response.json();
}