/** Dispara la descarga normal del navegador para un blob ya obtenido vía
 * `apiDownload()` — nunca abre el binario en pantalla. Compartido por la
 * exportación individual de artefactos y la exportación longitudinal del
 * Clinical Record (misma mecánica, dos consumidores). */
export function downloadFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
