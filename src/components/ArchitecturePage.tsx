import { useState, useRef, useCallback } from 'react'
import { marked } from 'marked'
import archContent from '../architecture.md?raw'

export default function ArchitecturePage() {
  const [downloading, setDownloading] = useState(false)
  const [pdfError, setPdfError] = useState('')
  const contentRef = useRef<HTMLDivElement>(null)

  const html = marked.parse(archContent, { async: false }) as string

  const downloadPdf = useCallback(async () => {
    if (!contentRef.current) return
    setDownloading(true)
    setPdfError('')
    try {
      const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([import('jspdf'), import('html2canvas')])
      const canvas = await html2canvas(contentRef.current, {
        scale: 2,
        backgroundColor: '#ffffff',
        useCORS: true,
      })
      const imgData = canvas.toDataURL('image/png')
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'pt', format: 'a4' })
      const pageWidth = pdf.internal.pageSize.getWidth()
      const pageHeight = pdf.internal.pageSize.getHeight()
      const margin = 36
      const usableWidth = pageWidth - margin * 2
      const imgWidth = usableWidth
      const imgHeight = (canvas.height * imgWidth) / canvas.width

      let heightLeft = imgHeight
      let position = margin

      pdf.addImage(imgData, 'PNG', margin, position, imgWidth, imgHeight)
      heightLeft -= pageHeight - margin

      while (heightLeft > 0) {
        position = heightLeft - imgHeight + margin
        pdf.addPage()
        pdf.addImage(imgData, 'PNG', margin, position, imgWidth, imgHeight)
        heightLeft -= pageHeight - margin * 2
      }

      pdf.save('architecture.pdf')
    } catch (err) {
      console.error('PDF generation failed:', err)
      setPdfError('The PDF could not be created. Try again, or print the page from your browser.')
    } finally {
      setDownloading(false)
    }
  }, [])

  return (
    <div>
      <div className="arch-head">
        <div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Application Architecture</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>
            Full system design, data flow, and component reference.
          </div>
        </div>
        <button className="btn btn-primary" onClick={downloadPdf} disabled={downloading}>
          {downloading ? (
            <>
              <span className="spinner" style={{ width: 14, height: 14, borderWidth: 1.5 }} />
              Generating…
            </>
          ) : (
            'Download as PDF'
          )}
        </button>
      </div>

      {pdfError && <div className="alert alert-error">{pdfError}</div>}

      <div ref={contentRef} className="arch-paper">
        <div
          className="arch-markdown"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    </div>
  )
}
