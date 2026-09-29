import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import { marked } from 'marked'
import './styles.css'

marked.setOptions({
  breaks: true,
  gfm: true,
})
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/esm/Page/AnnotationLayer.css'
import 'react-pdf/dist/esm/Page/TextLayer.css'

try {
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
  ).toString()
} catch {
  pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'
}

// ─── UTILITIES & HELPERS ────────────────────────────────────────────────────────

const formatFileSize = (bytes) => {
  if (!bytes && bytes !== 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const getDocName = (doc) => {
  if (!doc) return ''
  if (typeof doc === 'string') return doc
  return doc.filename || doc.original_filename || ''
}

const formatSourceTitle = (name) => {
  if (!name) return 'Tài liệu'
  return name.replace(/\.[^/.]+$/, '').replace(/_/g, ' ')
}

// Trích xuất các cụm từ và từ khóa quan trọng từ câu hỏi người dùng
const extractQueryKeywords = (query) => {
  if (!query || typeof query !== 'string') return []
  const stopWords = new Set([
    'la', 'là', 'gi', 'gì', 'nhu', 'như', 'the', 'thế', 'nao', 'nào',
    'o', 'ở', 'dau', 'đâu', 'khi', 'nao', 'nào', 'cho', 'biet', 'biết',
    'hay', 'hãy', 've', 'về', 'cua', 'của', 'cac', 'các', 'nhung', 'những',
    'thi', 'thì', 'phai', 'phải', 'co', 'có', 'khong', 'không', 'k', 'ko',
    'duoc', 'được', 'trong', 'voi', 'với', 'va', 'và', 'hay', 'ra', 'sao',
    'ai', 'may', 'mấy', 'bao', 'nhieu', 'nhiêu', 'bang', 'bằng', 'tai', 'tại',
    'theo', 'quy', 'dinh', 'định', 'toi', 'tôi', 'ban', 'bạn', 'em', 'anh', 'chi', 'chị'
  ])

  const clean = query.replace(/[?.,!;:"'()[\]{}]/g, ' ').trim()
  const words = clean.split(/\s+/).filter(w => w.length > 0)
  const keywords = []

  // 1. Cụm 3 từ liên tiếp (bắt trọn ngữ cảnh chính xác như: "chi nhánh ở tỉnh khác")
  for (let i = 0; i < words.length - 2; i++) {
    const w1 = words[i].toLowerCase()
    const w3 = words[i + 2].toLowerCase()
    if (!stopWords.has(w1) && !stopWords.has(w3)) {
      keywords.push(`${words[i]} ${words[i + 1]} ${words[i + 2]}`)
    }
  }

  // 2. Cụm 2 từ liên tiếp
  for (let i = 0; i < words.length - 1; i++) {
    const w1 = words[i].toLowerCase()
    const w2 = words[i + 1].toLowerCase()
    if (!stopWords.has(w1) || !stopWords.has(w2)) {
      keywords.push(`${words[i]} ${words[i + 1]}`)
    }
  }

  // 3. Từ đơn có ý nghĩa
  for (const w of words) {
    if (!stopWords.has(w.toLowerCase()) && w.length >= 2) {
      keywords.push(w)
    }
  }

  return Array.from(new Set(keywords)).sort((a, b) => b.length - a.length)
}

// Bôi đậm và highlight các từ khóa truy vấn trong văn bản
const highlightKeywords = (text, keywords) => {
  if (!text || !keywords || keywords.length === 0) return text
  const escaped = keywords.slice(0, 15).map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).filter(Boolean)
  if (escaped.length === 0) return text

  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')
  const parts = text.split(regex)

  return parts.map((part, i) => {
    if (regex.test(part)) {
      return (
        <mark
          key={i}
          className="bg-amber-400/30 dark:bg-amber-400/35 text-amber-950 dark:text-amber-200 font-bold px-1 py-0.5 rounded border border-amber-500/40 inline"
        >
          {part}
        </mark>
      )
    }
    return part
  })
}

// ─── SVG ICONS (MATCHING CHATGPT SPEC) ──────────────────────────────────────────

function Icon({ name, className = 'w-4 h-4', ...props }) {
  const icons = {
    sparkle: (
      <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z" />
    ),
    globe: (
      <>
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </>
    ),
    sidebarRight: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <line x1="15" y1="3" x2="15" y2="21" />
      </>
    ),
    x: (
      <>
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </>
    ),
    message: (
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    ),
    plus: (
      <path d="M12 5v14M5 12h14" />
    ),
    edit: (
      <>
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </>
    ),
    sidebar: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <line x1="9" y1="3" x2="9" y2="21" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </>
    ),
    library: (
      <>
        <rect x="4" y="4" width="4" height="16" rx="1" />
        <rect x="10" y="4" width="4" height="16" rx="1" />
        <rect x="16" y="4" width="4" height="16" rx="1" />
      </>
    ),
    star: (
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    ),
    tray: (
      <>
        <polyline points="4 17 10 17 12 19 14 17 20 17" />
        <path d="M5 17H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-1" />
        <line x1="12" y1="8" x2="12" y2="14" />
        <polyline points="9 11 12 14 15 11" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </>
    ),
    folder: (
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    ),
    arrowUp: (
      <path d="M12 19V5M5 12l7-7 7 7" />
    ),
    arrowLeft: (
      <path d="M19 12H5M12 19l-7-7 7-7" />
    ),
    chevronLeft: (
      <polyline points="15 18 9 12 15 6" />
    ),
    chevronRight: (
      <polyline points="9 18 15 12 9 6" />
    ),
    copy: (
      <>
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
      </>
    ),
    trash: (
      <>
        <polyline points="3 6 5 6 21 6" />
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </>
    ),
    sun: (
      <>
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </>
    ),
    moon: (
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    ),
    fileText: (
      <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </>
    ),
    check: (
      <polyline points="20 6 9 17 4 12" />
    ),
    checkCircle: (
      <>
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
        <polyline points="22 4 12 14.01 9 11.01" />
      </>
    ),
    mic: (
      <>
        <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="22" />
      </>
    ),
    share: (
      <>
        <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
        <polyline points="16 6 12 2 8 6" />
        <line x1="12" y1="2" x2="12" y2="15" />
      </>
    )
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {icons[name] || null}
    </svg>
  )
}

// ─── MAIN APP COMPONENT ─────────────────────────────────────────────────────────

export default function App() {
  const [isDark, setIsDark] = useState(() => localStorage.getItem('theme') !== 'light')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)

  // ─── HASH ROUTING helpers ───────────────────────────────────────────────────
  // Format:  #/chat            → mode=chat, id=null
  //          #/chat/123        → mode=chat, id='123'   (convId)
  //          #/documents       → mode=documents, id=null
  //          #/documents/abc   → mode=documents, id='abc' (docId)
  const parseHash = () => {
    const raw = window.location.hash.replace(/^#\/?/, '') // strip leading #/
    const [mode, id] = raw.split('/')
    if (mode === 'documents') return { mode: 'documents', id: id || null }
    return { mode: 'chat', id: id || null }  // default to chat
  }

  const pushHash = (mode, id = null) => {
    const next = id ? `#/${mode}/${id}` : `#/${mode}`
    if (window.location.hash !== next) {
      window.history.pushState(null, '', next)
    }
  }

  // 'chat' | 'documents'
  const [mainMode, setMainMode] = useState(() => parseHash().mode)

  // Real Database Documents
  const [documents, setDocuments] = useState([])
  const [selectedDocId, setSelectedDocId] = useState(() => {
    const { mode, id } = parseHash()
    return mode === 'documents' ? id : null
  })
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [uploading, setUploading] = useState(false)

  // Real Database Conversations
  const [conversations, setConversations] = useState([])
  const [activeConvId, setActiveConvId] = useState(() => {
    const { mode, id } = parseHash()
    return mode === 'chat' ? id : null
  })

  // Real Extraction Data
  const [extractionData, setExtractionData] = useState(null)
  const [loadingExtraction, setLoadingExtraction] = useState(false)

  // PDF Viewer States
  const [numPages, setNumPages] = useState(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageScale, setPageScale] = useState(1.0)
  const [showOcrBoxes, setShowOcrBoxes] = useState(true)
  const [pdfBlobUrl, setPdfBlobUrl] = useState(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState(false)
  const [useNativePdf, setUseNativePdf] = useState(false)

  // Markdown States
  const [mdViewMode, setMdViewMode] = useState('rendered')
  const [copiedMd, setCopiedMd] = useState(false)

  // Chat State
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [searchingQuery, setSearchingQuery] = useState('')
  const [queryingDocIndex, setQueryingDocIndex] = useState(0)
  const chatBottomRef = useRef(null)
  const fileInputRef = useRef(null)
  const chatInputRef = useRef(null)

  // Hiệu ứng cập nhật hiển thị tài liệu liên tục khi đang truy vấn RAG
  useEffect(() => {
    if (!chatLoading || !documents || documents.length === 0) {
      setQueryingDocIndex(0)
      return
    }
    const interval = setInterval(() => {
      setQueryingDocIndex(prev => (prev + 1) % documents.length)
    }, 700)
    return () => clearInterval(interval)
  }, [chatLoading, documents])

  // Kiểm tra văn bản nhập vào có phải nhiều dòng không (để chuyển từ 1 dòng sang hình hộp)
  const isInputMultiline = useMemo(() => {
    if (!chatInput) return false
    if (chatInput.includes('\n')) return true
    return chatInput.length > 55
  }, [chatInput])

  // Auto-resize chat textarea linh hoạt theo nội dung khi ở chế độ nhiều dòng (tối đa 280px)
  useEffect(() => {
    if (chatInputRef.current) {
      if (isInputMultiline) {
        chatInputRef.current.style.height = 'auto'
        const scrollH = chatInputRef.current.scrollHeight
        chatInputRef.current.style.height = `${Math.min(Math.max(scrollH, 54), 280)}px`
      } else {
        chatInputRef.current.style.height = '24px'
      }
    }
  }, [chatInput, isInputMultiline])

  // Tự động cuộn mượt mà xuống sát đáy khi có câu hỏi mới hoặc tin nhắn mới
  useEffect(() => {
    if (chatMessages.length > 0 || chatLoading) {
      const timer = setTimeout(() => {
        chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 60)
      return () => clearTimeout(timer)
    }
  }, [chatMessages, chatLoading])

  // Chat Right Sidebar States (View file in chat - SINGLE DOCUMENT FOCUSED)
  const [chatSidebarOpen, setChatSidebarOpen] = useState(false)
  const [chatActiveDocId, setChatActiveDocId] = useState(null)
  const [chatActiveDocName, setChatActiveDocName] = useState('')
  const [chatActiveSources, setChatActiveSources] = useState([])
  const [chatActiveChunks, setChatActiveChunks] = useState([])
  const [chatActiveQuery, setChatActiveQuery] = useState('')
  const [chatSidebarTab, setChatSidebarTab] = useState('chunks') // 'chunks' | 'preview'
  const [chatDocBlobUrl, setChatDocBlobUrl] = useState(null)
  const [chatDocLoading, setChatDocLoading] = useState(false)
  const [chatDocError, setChatDocError] = useState(false)
  const [chatDocUseNative, setChatDocUseNative] = useState(false)
  const [chatDocNumPages, setChatDocNumPages] = useState(null)
  const [chatDocPage, setChatDocPage] = useState(1)

  // Copied message feedback
  const [copiedMsgId, setCopiedMsgId] = useState(null)

  const handleCopyMessage = (text, id) => {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopiedMsgId(id)
    setTimeout(() => setCopiedMsgId(null), 2000)
  }

  const handleShareMessage = async (text) => {
    if (!text) return
    if (navigator.share) {
      try {
        await navigator.share({ text })
        return
      } catch {}
    }
    navigator.clipboard.writeText(text)
    alert('Đã sao chép nội dung để chia sẻ')
  }

  // Helper to resolve document ID
  const resolveDocId = (docIdOrName) => {
    if (!docIdOrName) return null
    const byId = documents.find(d => String(d.id) === String(docIdOrName))
    if (byId) return byId.id
    const byName = documents.find(d => getDocName(d) === docIdOrName || d.original_filename === docIdOrName)
    if (byName) return byName.id
    return docIdOrName
  }

  // Lọc danh sách chunks chỉ thuộc về 1 tài liệu đang xem ở sidebar
  const filteredChunks = useMemo(() => {
    if (!chatActiveChunks || chatActiveChunks.length === 0) return []
    return chatActiveChunks.filter(c => {
      const meta = c.metadata || {}
      const cDocId = meta.document_id || c.document_id
      const cFileName = meta.filename || c.file_name
      if (chatActiveDocId && cDocId) {
        return String(cDocId) === String(chatActiveDocId)
      }
      if (chatActiveDocName && cFileName) {
        return cFileName === chatActiveDocName || formatSourceTitle(cFileName) === formatSourceTitle(chatActiveDocName)
      }
      return true
    })
  }, [chatActiveChunks, chatActiveDocId, chatActiveDocName])

  // Trích xuất từ khóa truy vấn để bôi đậm chính xác
  const queryKeywords = useMemo(() => {
    return extractQueryKeywords(chatActiveQuery || searchingQuery || '')
  }, [chatActiveQuery, searchingQuery])

  // Custom text renderer cho PDF TextLayer để bôi đậm từ khóa trực tiếp trên trang PDF
  const customTextRenderer = useCallback((textItem) => {
    if (!queryKeywords || queryKeywords.length === 0) return textItem.str
    return highlightKeywords(textItem.str, queryKeywords)
  }, [queryKeywords])

  // Effect to fetch preview for file in chat right sidebar
  useEffect(() => {
    if (!chatSidebarOpen || !chatActiveDocId) return

    const resolvedId = resolveDocId(chatActiveDocId)
    if (!resolvedId) return

    let isSubscribed = true
    setChatDocLoading(true)
    setChatDocError(false)
    setChatDocPage(1)

    fetch(`/api/documents/${resolvedId}/preview`, { credentials: 'include' })
      .then(res => {
        if (!res.ok) {
          return fetch(`/api/documents/${resolvedId}/content`, { credentials: 'include' })
        }
        return res
      })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.blob()
      })
      .then(blob => {
        if (!isSubscribed) return
        const pdfBlob = blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' })
        const url = URL.createObjectURL(pdfBlob)
        setChatDocBlobUrl(url)
        setChatDocLoading(false)
      })
      .catch(err => {
        console.error('Lỗi tải tài liệu trong chat sidebar:', err)
        if (isSubscribed) {
          setChatDocError(true)
          setChatDocLoading(false)
        }
      })

    return () => {
      isSubscribed = false
    }
  }, [chatActiveDocId, chatSidebarOpen, documents])

  // Chỉ mở 1 tài liệu 1 lần trong sidebar
  const handleOpenSourceInSidebar = (docIdOrName, fileName, sources = [], chunks = [], pageNo = 1, query = '') => {
    const resolvedId = resolveDocId(docIdOrName) || resolveDocId(fileName)
    setChatActiveDocId(resolvedId || docIdOrName)
    setChatActiveDocName(fileName || docIdOrName)
    // Chỉ lưu 1 tài liệu duy nhất đang active
    setChatActiveSources(sources.length > 0 ? [sources[0]] : [{ file_name: fileName, document_id: resolvedId || docIdOrName }])
    setChatActiveChunks(chunks.length > 0 ? chunks : (chatActiveChunks || []))
    if (query) {
      setChatActiveQuery(query)
    } else if (searchingQuery) {
      setChatActiveQuery(searchingQuery)
    }
    if (pageNo && typeof pageNo === 'number') {
      setChatDocPage(pageNo)
    }
    setChatSidebarOpen(true)
  }

  // Authenticated User
  const [currentUser, setCurrentUser] = useState('admin')

  // Ambient Mouse Follower Glow (Phet loang sang theo con tro chuot)
  useEffect(() => {
    let rafId
    const updateMousePos = (e) => {
      cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => {
        document.documentElement.style.setProperty('--mouse-x', `${e.clientX}px`)
        document.documentElement.style.setProperty('--mouse-y', `${e.clientY}px`)
      })
    }
    window.addEventListener('pointermove', updateMousePos, { passive: true })
    return () => {
      window.removeEventListener('pointermove', updateMousePos)
      cancelAnimationFrame(rafId)
    }
  }, [])

  // Auto Theme
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark')
      document.documentElement.setAttribute('data-theme', 'dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      document.documentElement.removeAttribute('data-theme')
      localStorage.setItem('theme', 'light')
    }
  }, [isDark])

  // ─── HASH ROUTING: Write hash when navigation state changes ────────────────
  useEffect(() => {
    if (mainMode === 'documents') {
      pushHash('documents', selectedDocId)
    } else {
      pushHash('chat', activeConvId)
    }
  }, [mainMode, selectedDocId, activeConvId])

  // ─── HASH ROUTING: Listen to browser back/forward and F5 ──────────────────
  useEffect(() => {
    const onHashChange = () => {
      const { mode, id } = parseHash()
      setMainMode(mode)
      if (mode === 'documents') {
        setSelectedDocId(id)
      } else {
        setActiveConvId(id)
        if (!id) {
          setChatMessages([])
          setChatInput('')
        }
      }
    }
    window.addEventListener('popstate', onHashChange)
    window.addEventListener('hashchange', onHashChange)
    return () => {
      window.removeEventListener('popstate', onHashChange)
      window.removeEventListener('hashchange', onHashChange)
    }
  }, [])

  // Authentication & Session
  const checkAuth = async () => {
    try {
      const res = await fetch('/api/auth/me')
      if (res.ok) {
        const data = await res.json()
        setCurrentUser(data.username || data.user || 'admin')
      } else {
        autoLogin()
      }
    } catch {
      autoLogin()
    }
  }

  const autoLogin = async () => {
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'matkhausieudai123' })
      })
      if (res.ok) {
        const data = await res.json()
        setCurrentUser(data.username || 'admin')
        if (data.csrf_token) {
          localStorage.setItem('csrf_token', data.csrf_token)
        }
        fetchDocuments()
        fetchConversations()
      }
    } catch (err) {
      console.error(err)
    }
  }

  // Fetch Real Documents
  const fetchDocuments = async () => {
    try {
      setLoadingDocs(true)
      const res = await fetch('/api/documents?page=1&size=50')
      if (res.ok) {
        const data = await res.json()
        const docs = data.items || data.documents || []
        setDocuments(docs)
      }
    } catch (err) {
      console.error('Error fetching documents:', err)
    } finally {
      setLoadingDocs(false)
    }
  }

  // Fetch Real Conversations from Database
  const fetchConversations = async () => {
    try {
      const res = await fetch('/api/conversations')
      if (res.ok) {
        const data = await res.json()
        setConversations(data || [])
      }
    } catch (err) {
      console.error('Error fetching conversations:', err)
    }
  }

  const hasProcessingDocs = useMemo(() => {
    return documents.some(d => d.status === 'queued' || d.status === 'processing')
  }, [documents])

  useEffect(() => {
    checkAuth()
    fetchDocuments()
    fetchConversations()
  }, [])

  useEffect(() => {
    const delay = hasProcessingDocs ? 1500 : 6000
    const interval = setInterval(() => {
      fetchDocuments()
      fetchConversations()
    }, delay)
    return () => clearInterval(interval)
  }, [hasProcessingDocs])

  // Selected document (NO fallback to docs[0] so preview only shows when explicitly selected)
  const currentDoc = useMemo(() => {
    if (!selectedDocId) return null
    return documents.find(d => String(d.id) === String(selectedDocId)) || null
  }, [documents, selectedDocId])

  // Active conversation
  const activeConversation = useMemo(() => {
    if (!activeConvId) return null
    return conversations.find(c => String(c.id) === String(activeConvId)) || null
  }, [conversations, activeConvId])

  // Fetch Extraction Data for Active Document
  useEffect(() => {
    if (!selectedDocId) {
      setExtractionData(null)
      return
    }
    setLoadingExtraction(true)
    fetch(`/api/documents/${selectedDocId}/extraction`)
      .then(r => r.json())
      .then(d => {
        setExtractionData(d)
        setLoadingExtraction(false)
      })
      .catch(() => setLoadingExtraction(false))
  }, [selectedDocId])

  // Poll document status every 2s when queued/processing
  useEffect(() => {
    if (!currentDoc) return
    const isProcessing = currentDoc.status === 'queued' || currentDoc.status === 'processing'
    if (!isProcessing) return

    const intervalId = setInterval(async () => {
      try {
        const res = await fetch(`/api/documents?page=1&size=50`)
        if (res.ok) {
          const data = await res.json()
          const docs = data.items || data.documents || []
          setDocuments(docs)
          const updated = docs.find(d => String(d.id) === String(selectedDocId))
          if (updated && updated.status !== 'queued' && updated.status !== 'processing') {
            clearInterval(intervalId)
            if (updated.status === 'processed') {
              fetch(`/api/documents/${selectedDocId}/extraction`)
                .then(r => r.json())
                .then(d => setExtractionData(d))
                .catch(() => {})
            }
          }
        }
      } catch (err) {
        console.error('Polling error:', err)
      }
    }, 2000)

    return () => clearInterval(intervalId)
  }, [currentDoc?.status, currentDoc?.id])

  // Fetch PDF Preview Blob for Active Document (only when processed)
  useEffect(() => {
    if (!currentDoc?.id || currentDoc.status !== 'processed') {
      setPdfBlobUrl(null)
      return
    }
    let isSubscribed = true
    setPdfLoading(true)

    fetch(`/api/documents/${currentDoc.id}/preview`, { credentials: 'include' })
      .then(res => {
        if (!res.ok) {
          return fetch(`/api/documents/${currentDoc.id}/content`, { credentials: 'include' })
        }
        return res
      })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.blob()
      })
      .then(blob => {
        if (!isSubscribed) return
        const pdfBlob = blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' })
        const url = URL.createObjectURL(pdfBlob)
        setPdfBlobUrl(url)
        setPdfError(false)
        setPdfLoading(false)
      })
      .catch((err) => {
        console.error('Loi tai PDF blob:', err)
        if (isSubscribed) {
          setPdfError(true)
          setPdfLoading(false)
        }
      })

    return () => {
      isSubscribed = false
    }
  }, [currentDoc?.id, currentDoc?.status])

  // Handle Conversation Selection
  const selectConversation = async (convId) => {
    setActiveConvId(convId)
    setMainMode('chat')
    pushHash('chat', convId)
    try {
      setChatLoading(true)
      const res = await fetch(`/api/conversations/${convId}`)
      if (res.ok) {
        const data = await res.json()
        const msgs = (data.messages || []).map(m => ({
          id: m.id,
          role: m.role,
          text: m.content,
          sources: m.sources || [],
          retrieved_chunks: m.retrieved_chunks || [],
          searchQuery: m.search_query || ''
        }))
        setChatMessages(msgs)
        // Auto-select first source if available
        const lastWithSources = [...msgs].reverse().find(m => m.sources && m.sources.length > 0)
        if (lastWithSources) {
          setChatActiveSources(lastWithSources.sources)
          setChatActiveChunks(lastWithSources.retrieved_chunks || [])
          const first = lastWithSources.sources[0]
          setChatActiveDocId(resolveDocId(first.document_id || first.file_name))
          setChatActiveDocName(first.file_name)
        }
      }
    } catch (err) {
      console.error('Error loading conversation messages:', err)
    } finally {
      setChatLoading(false)
      setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    }
  }

  // Handle Starting a New Conversation
  const handleNewChat = () => {
    setActiveConvId(null)
    setChatMessages([])
    setChatInput('')
    setMainMode('chat')
    pushHash('chat', null)
  }

  // Delete Conversation
  const handleDeleteConversation = async (e, convId) => {
    e.stopPropagation()
    if (!window.confirm('Bạn có chắc muốn xóa cuộc trò chuyện này?')) return
    try {
      const res = await fetch(`/api/conversations/${convId}`, { method: 'DELETE' })
      if (res.ok) {
        setConversations(prev => prev.filter(c => c.id !== convId))
        if (activeConvId === convId) {
          handleNewChat()
        }
      }
    } catch (err) {
      console.error('Error deleting conversation:', err)
    }
  }

  // Delete Document
  const handleDeleteDoc = async (e, docId) => {
    e.stopPropagation()
    if (!window.confirm('Bạn có chắc muốn xóa tài liệu này khỏi hệ thống?')) return
    try {
      const res = await fetch(`/api/documents/${docId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'X-CSRF-Token': localStorage.getItem('csrf_token') || ''
        }
      })
      if (res.ok) {
        setDocuments(prev => prev.filter(d => d.id !== docId))
        if (selectedDocId === docId) {
          setSelectedDocId(null)
          setExtractionData(null)
          setPdfBlobUrl(null)
        }
      } else {
        const err = await res.json().catch(() => ({}))
        alert(`Không thể xóa tài liệu: ${err.detail || res.statusText}`)
      }
    } catch (err) {
      console.error('Error deleting document:', err)
      alert(`Lỗi kết nối khi xóa tài liệu: ${err.message}`)
    }
  }

  // Upload File
  const handleFileUpload = async (files) => {
    if (!files || files.length === 0) return
    setUploading(true)

    const formData = new FormData()
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i])
    }

    try {
      const res = await fetch('/api/documents', {
        method: 'POST',
        body: formData
      })
      if (res.ok) {
        const data = await res.json()
        await fetchDocuments()
        if (data.uploaded && data.uploaded[0]) {
          const newDocId = data.uploaded[0].id
          setSelectedDocId(newDocId)
          setMainMode('documents')
          pushHash('documents', newDocId)
        }
      }
    } catch (err) {
      console.error(err)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  // Real RAG Chat Handler (Persisting into PostgreSQL database)
  const handleSendChat = async (presetText) => {
    const query = (presetText || chatInput).trim()
    if (!query || chatLoading) return

    const tempUserMsg = { role: 'user', text: query }
    setChatMessages(prev => [...prev, tempUserMsg])
    if (!presetText) setChatInput('')
    setChatLoading(true)
    setSearchingQuery(query)

    try {
      let targetConvId = activeConvId
      if (!targetConvId) {
        const createRes = await fetch('/api/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: query.slice(0, 50) })
        })
        if (createRes.ok) {
          const convData = await createRes.json()
          targetConvId = convData.id
          setActiveConvId(targetConvId)
        }
      }

      const bodyPayload = {
        question: query,
        top_k: 10
      }

      const res = await fetch(`/api/conversations/${targetConvId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyPayload)
      })

      if (res.ok) {
        const data = await res.json()
        const sources = data.sources || []
        const chunks = data.retrieved_chunks || []
        setChatMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            text: data.answer || 'Không tìm thấy câu trả lời phù hợp trong tài liệu.',
            sources: sources,
            retrieved_chunks: chunks,
            searchQuery: query
          }
        ])
        if (sources.length > 0) {
          setChatActiveSources(sources)
          setChatActiveChunks(chunks)
          if (!chatActiveDocId) {
            const first = sources[0]
            setChatActiveDocId(resolveDocId(first.document_id || first.file_name))
            setChatActiveDocName(first.file_name)
          }
        }
        fetchConversations()
      } else {
        setChatMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            text: 'Không thể xử lý truy vấn RAG lúc này. Vui lòng thử lại.',
            searchQuery: query
          }
        ])
      }
    } catch (err) {
      setChatMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: `Lỗi kết nối API: ${err.message}`,
          searchQuery: query
        }
      ])
    } finally {
      setChatLoading(false)
      setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    }
  }

  // API /extraction returns: { status, filename, extracted_data }
  // extracted_data has: ocr_text (string), chunks ([{id, text, metadata}]), semantic_structure, etc.
  const extractedObj = extractionData?.extracted_data || extractionData?.extraction || {}
  const fullMarkdown = (
    extractedObj.normalized_markdown ||
    extractedObj.raw_markdown ||
    extractedObj.ocr_text ||
    ''
  )
  // chunks may use field 'text' or 'content'
  const rawChunks = extractedObj.chunks || []
  const chunks = rawChunks.map((c, i) => ({
    ...c,
    chunk_index: c.chunk_index ?? c.index ?? (i + 1),
    content: c.content || c.text || ''
  }))

  return (
    <div className="h-screen w-screen p-2 md:p-3 flex overflow-hidden gap-2 md:gap-3 bg-[var(--bg-canvas-gradient)] relative">
      {/* Phết loang sáng theo con trỏ chuột */}
      <div className="ambient-mouse-glow" aria-hidden="true" />

      <input
        type="file"
        ref={fileInputRef}
        onChange={(e) => handleFileUpload(e.target.files)}
        multiple
        accept=".pdf,.docx,.pptx,.xlsx,.txt,.md"
        className="hidden"
      />

      {/* ─── 1. SLIM FLOATING VERTICAL DOCK (EXACT MATCH TO USER SCREENSHOT) ─── */}
      <aside className="w-14 shrink-0 flex flex-col justify-between items-center py-4 px-1.5 floating-vertical-dock z-30">
        {/* Top: Back Arrow Circle Button */}
        <button
          onClick={() => setIsSidebarOpen(open => !open)}
          className="circle-btn w-9 h-9 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          title={isSidebarOpen ? "Thu gọn danh sách" : "Mở rộng danh sách"}
        >
          <Icon name="arrowLeft" className={`w-4 h-4 transition-transform duration-200 ${isSidebarOpen ? '' : 'rotate-180'}`} />
        </button>

        {/* Center Group: Vertical Stack of Circular Icons */}
        <div className="flex flex-col items-center gap-3.5 w-full py-2">
          {/* Chat Icon */}
          <button
            onClick={() => { setMainMode('chat'); pushHash('chat', activeConvId) }}
            className={`transition ${
              mainMode === 'chat'
                ? 'active-dock-chat-btn'
                : 'circle-btn w-9 h-9 text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
            title="Hỏi đáp AI (Chat)"
          >
            <Icon name="message" className="w-4 h-4" />
          </button>

          {/* Folder / Library Icon */}
          <button
            onClick={() => { setMainMode('documents'); pushHash('documents', selectedDocId) }}
            className={`transition ${
              mainMode === 'documents'
                ? 'active-dock-chat-btn'
                : 'circle-btn w-9 h-9 text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
            title="Kho tài liệu tri thức"
          >
            <Icon name="folder" className="w-4 h-4" />
          </button>
        </div>

        {/* Bottom Group */}
        <div className="flex flex-col items-center gap-3.5 w-full">
          {/* Upload Tray Button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="circle-btn w-9 h-9 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            title="Tải lên tài liệu PDF/DOCX"
          >
            <Icon name="tray" className="w-4 h-4" />
          </button>

          {/* Settings / Theme Toggle Button */}
          <button
            onClick={() => setIsDark(d => !d)}
            className="circle-btn w-9 h-9 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            title={isDark ? "Chuyển sang Chế độ Sáng" : "Chuyển sang Chế độ Tối"}
          >
            <Icon name="settings" className="w-4 h-4" />
          </button>

          {/* User Avatar Portrait */}
          <div
            className="w-9 h-9 rounded-full overflow-hidden border border-black/10 dark:border-white/20 shadow-xs flex items-center justify-center bg-gradient-to-tr from-blue-500 via-indigo-500 to-purple-500 text-white font-bold text-xs shrink-0 cursor-pointer"
            title={`Người dùng: ${currentUser}`}
          >
            {currentUser.slice(0, 2).toUpperCase()}
          </div>
        </div>
      </aside>

      {/* ─── 2. SECONDARY LIST PANEL (COLLAPSIBLE) ─── */}
      <aside
        className={`flex flex-col justify-between h-full select-none transition-all duration-200 z-20 shrink-0 rounded-3xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/[0.03] backdrop-blur-xl ${
          isSidebarOpen ? 'w-64 p-3' : 'w-0 overflow-hidden opacity-0 pointer-events-none p-0 border-0 m-0'
        }`}
      >
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-1 pb-3 border-b border-black/5 dark:border-white/10">
            <span className="font-bold text-xs tracking-wider uppercase text-[var(--text-muted)]">
              {mainMode === 'chat' ? 'Hội thoại gần đây' : `Kho tài liệu (${documents.length})`}
            </span>
            {mainMode === 'documents' ? (
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-7 h-7 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 text-[var(--text-primary)] flex items-center justify-center transition"
                title="Tải lên tài liệu mới"
              >
                <Icon name="plus" className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleNewChat}
                className="w-7 h-7 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 text-[var(--text-primary)] flex items-center justify-center transition"
                title="Cuộc trò chuyện mới"
              >
                <Icon name="plus" className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Items List */}
          <div className="flex-1 overflow-y-auto space-y-1.5 pt-3 pr-1">
            {mainMode === 'chat' ? (
              conversations.length === 0 ? (
                <div className="px-3 py-6 text-xs text-[var(--text-muted)] text-center">
                  Chưa có hội thoại nào.
                </div>
              ) : (
                conversations.map(c => {
                  const isActive = String(c.id) === String(activeConvId)
                  return (
                    <div
                      key={c.id}
                      onClick={() => selectConversation(c.id)}
                      className={`group relative flex items-center justify-between px-3 py-2.5 rounded-xl text-xs md:text-sm cursor-pointer transition border ${
                        isActive
                          ? 'active-glow-card'
                          : 'bg-white/40 dark:bg-white/[0.03] hover:bg-white/80 dark:hover:bg-white/[0.07] border-black/5 dark:border-white/[0.06] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                      }`}
                    >
                      <span className="truncate flex-1 text-left font-medium">
                        {c.title || 'Hội thoại mới'}
                      </span>
                      <button
                        onClick={(e) => handleDeleteConversation(e, c.id)}
                        className="opacity-0 group-hover:opacity-100 hover:text-red-500 p-1 rounded transition text-[var(--text-muted)] ml-1 shrink-0"
                        title="Xóa cuộc trò chuyện"
                      >
                        <Icon name="trash" className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )
                })
              )
            ) : (
              documents.length === 0 ? (
                <div className="px-3 py-6 text-xs text-[var(--text-muted)] text-center">
                  Chưa có tài liệu nào.
                </div>
              ) : (
                documents.map(d => {
                  const isSelected = String(d.id) === String(selectedDocId)
                  return (
                    <div
                      key={d.id}
                      onClick={() => { setSelectedDocId(d.id); pushHash('documents', d.id) }}
                      className={`group relative flex items-center justify-between p-2.5 rounded-xl cursor-pointer transition border ${
                        isSelected
                          ? 'active-glow-card'
                          : 'bg-white/40 dark:bg-white/[0.03] hover:bg-white/80 dark:hover:bg-white/[0.07] border-black/5 dark:border-white/[0.06] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider shrink-0 ${
                          isSelected ? 'bg-white/20 text-white' : 'bg-black/5 dark:bg-white/10 text-[var(--text-secondary)]'
                        }`}>
                          {getDocName(d).toLowerCase().endsWith('.pdf') ? 'PDF' : 'DOC'}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-semibold" title={getDocName(d)}>
                            {getDocName(d)}
                          </p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className={`text-[10px] ${isSelected ? 'opacity-80' : 'text-[var(--text-muted)]'}`}>
                              {formatFileSize(d.size_bytes)}
                            </span>
                            {d.status === 'processing' && (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-amber-500/15 text-amber-500 dark:text-amber-400 border border-amber-500/30 shrink-0">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                                {d.progress || 0}%
                              </span>
                            )}
                            {d.status === 'queued' && (
                              <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[9px] font-medium bg-blue-500/15 text-blue-500 dark:text-blue-400 border border-blue-500/30 shrink-0">
                                Chờ lượt
                              </span>
                            )}
                            {d.status === 'failed' && (
                              <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[9px] font-medium bg-red-500/15 text-red-500 border border-red-500/30 shrink-0">
                                Lỗi
                              </span>
                            )}
                            {d.status === 'processed' && (
                              <span className="text-[10px] text-emerald-500 font-bold ml-auto shrink-0" title="Đã xử lý xong">
                                ✓
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDeleteDoc(e, d.id)}
                        className="opacity-0 group-hover:opacity-100 hover:text-red-500 p-1 rounded transition text-[var(--text-muted)] ml-1 shrink-0"
                        title="Xóa tài liệu"
                      >
                        <Icon name="trash" className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )
                })
              )
            )}
          </div>
        </div>
      </aside>

      {/* ─── 3. MAIN WORKSPACE (TABLET FRAME) ─── */}
      <main className="bubble-tablet-frame flex-1 flex flex-col h-full overflow-hidden relative">

        {/* ═══ VIEW A: CHAT WORKSPACE (HỘI THOẠI) ═══ */}
        {mainMode === 'chat' && (
          <div className="flex-1 flex flex-col h-full overflow-hidden">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={e => handleFileUpload(e.target.files)}
            />
            {/* Top Bar */}
            <header className="h-12 px-5 border-b border-black/5 dark:border-white/10 flex items-center justify-between shrink-0 pl-14 sm:pl-5">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-[var(--text-primary)] truncate max-w-md">
                  {activeConversation ? activeConversation.title : 'Cuộc trò chuyện mới'}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleNewChat}
                  className="w-8 h-8 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 text-[var(--text-primary)] flex items-center justify-center transition cursor-pointer"
                  title="Cuộc trò chuyện mới"
                >
                  <Icon name="plus" className="w-4 h-4" />
                </button>
                {/* Nút bật/tắt xem tài liệu ở sidebar bên phải */}
                <button
                  onClick={() => setChatSidebarOpen(prev => !prev)}
                  className={`h-8 px-2.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                    chatSidebarOpen
                      ? 'bg-blue-600 text-white border-blue-600 shadow-xs'
                      : 'border-black/10 dark:border-white/10 text-[var(--text-secondary)] hover:bg-black/5 dark:hover:bg-white/10'
                  }`}
                  title={chatSidebarOpen ? "Đóng khung xem tài liệu bên phải" : "Mở khung xem tài liệu bên phải"}
                >
                  <Icon name="sidebarRight" className="w-4 h-4" />
                  <span className="hidden sm:inline">Xem tài liệu</span>
                  {(() => {
                    const uniqueDocCount = new Set((chatActiveSources || []).map(s => s.file_name || s.document_id).filter(Boolean)).size
                    const chunkCount = chatActiveSources.length
                    if (uniqueDocCount === 0) return null
                    return (
                      <span
                        className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                          chatSidebarOpen ? 'bg-white/20 text-white' : 'bg-black/10 dark:bg-white/10'
                        }`}
                        title={`${chunkCount} đoạn trích từ ${uniqueDocCount} tài liệu`}
                      >
                        {uniqueDocCount}
                      </span>
                    )
                  })()}
                </button>
              </div>
            </header>

            {/* Split layout: Chat body on Left, Document Viewer Sidebar on Right */}
            <div className="flex-1 flex overflow-hidden">
              {/* TRẠNG THÁI 1: KHUNG CHAT RA CHÍNH GIỮA (KHI CHƯA NHẮN TIN) */}
              {chatMessages.length === 0 && !chatLoading ? (
                <div className="flex-1 flex flex-col justify-between items-center p-4 sm:p-6 min-w-0 w-full relative">
                  <div />
                  {/* Hero Box & Khung nhập chat ra giữa */}
                  <div className="w-full max-w-2xl sm:max-w-3xl px-4 flex flex-col items-center -mt-8">
                    <h2 className="text-2xl sm:text-3xl font-medium text-[var(--text-primary)] mb-6 sm:mb-8 text-center tracking-tight select-none">
                      Tôi có thể giúp gì cho bạn hôm nay?
                    </h2>

                    {/* Khung nhập chat chuyển đổi thông minh: 1 dòng ban đầu, hộp khi đủ dài (như hình 1 & 2) */}
                    {!isInputMultiline ? (
                      /* DẠNG 1 DÒNG BAN ĐẦU */
                      <div className="w-full rounded-full border border-black/10 dark:border-white/10 bg-white/70 dark:bg-[#212121] shadow-md transition-all duration-200 px-2 sm:px-2.5 py-1.5 flex items-center gap-2 focus-within:border-zinc-400 dark:focus-within:border-zinc-500">
                        <button
                          type="button"
                          onClick={() => fileInputRef.current?.click()}
                          className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                          title="Tải lên tài liệu"
                        >
                          <Icon name="plus" className="w-4 h-4 stroke-[2.5]" />
                        </button>

                        <textarea
                          ref={chatInputRef}
                          rows={1}
                          value={chatInput}
                          onChange={e => setChatInput(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault()
                              handleSendChat()
                            }
                          }}
                          placeholder="Hỏi bất kỳ điều gì..."
                          spellCheck={false}
                          autoComplete="off"
                          className="flex-1 bg-transparent border-none outline-none text-xs sm:text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] resize-none leading-normal py-1 px-1 font-normal overflow-hidden h-6 min-h-[24px]"
                          style={{ height: '24px', minHeight: '24px', maxHeight: '24px' }}
                        />

                        <button
                          type="button"
                          className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                          title="Nhập bằng giọng nói"
                        >
                          <Icon name="mic" className="w-4 h-4" />
                        </button>

                        <button
                          type="button"
                          onClick={() => handleSendChat()}
                          disabled={!chatInput.trim()}
                          className={`w-8 h-8 rounded-full flex items-center justify-center transition shrink-0 ${
                            chatInput.trim()
                              ? 'bg-zinc-900 text-white dark:bg-white dark:text-black shadow-xs cursor-pointer hover:opacity-90'
                              : 'bg-black/10 dark:bg-white/10 text-[var(--text-muted)] opacity-40 cursor-not-allowed'
                          }`}
                          title="Gửi câu hỏi"
                        >
                          <Icon name="arrowUp" className="w-4 h-4 stroke-[2.5]" />
                        </button>
                      </div>
                    ) : (
                      /* DẠNG NHIỀU DÒNG (HÌNH 1 & HÌNH 2: TỰ CO GIÃN THEO VĂN BẢN, TỐI ĐA 280PX KÈM SCROLL) */
                      <div className="w-full rounded-3xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-[#212121] shadow-lg transition-all duration-200 p-3 sm:p-3.5 flex flex-col focus-within:border-zinc-400 dark:focus-within:border-zinc-500 animate-in fade-in-50 duration-150">
                        <textarea
                          ref={chatInputRef}
                          value={chatInput}
                          onChange={e => setChatInput(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault()
                              handleSendChat()
                            }
                          }}
                          placeholder="Hỏi bất kỳ điều gì..."
                          spellCheck={false}
                          autoComplete="off"
                          className="w-full bg-transparent border-none outline-none text-xs sm:text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] resize-none leading-relaxed px-1.5 py-1 overflow-y-auto"
                          style={{ minHeight: '54px', maxHeight: '280px' }}
                        />

                        <div className="flex items-center justify-between pt-2 px-1">
                          <button
                            type="button"
                            onClick={() => fileInputRef.current?.click()}
                            className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                            title="Tải lên tài liệu"
                          >
                            <Icon name="plus" className="w-4 h-4 stroke-[2.5]" />
                          </button>

                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                              title="Nhập bằng giọng nói"
                            >
                              <Icon name="mic" className="w-4 h-4" />
                            </button>

                            <button
                              type="button"
                              onClick={() => handleSendChat()}
                              disabled={!chatInput.trim()}
                              className={`w-8 h-8 rounded-full flex items-center justify-center transition shrink-0 ${
                                chatInput.trim()
                                  ? 'bg-zinc-900 text-white dark:bg-white dark:text-black shadow-xs cursor-pointer hover:opacity-90'
                                  : 'bg-black/10 dark:bg-white/10 text-[var(--text-muted)] opacity-40 cursor-not-allowed'
                              }`}
                              title="Gửi câu hỏi"
                            >
                              <Icon name="arrowUp" className="w-4 h-4 stroke-[2.5]" />
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Dòng cảnh báo AI dưới đáy */}
                  <div className="w-full text-center pb-2 px-4 select-none">
                    <p className="text-[11.5px] text-[var(--text-muted)] font-normal">
                      AI có thể mắc lỗi. Vui lòng kiểm tra lại các thông tin quan trọng.
                    </p>
                  </div>
                </div>
              ) : (
                /* TRẠNG THÁI 2: KHI ĐÃ NHẮN TIN - KHUNG NHẬP NHẢY XUỐNG DƯỚI ĐÁY */
                <div className="flex-1 flex flex-col justify-between overflow-hidden relative p-4 md:p-6 min-w-0">
                  <div className="flex-1 overflow-y-auto pr-2 space-y-6 max-w-3xl xl:max-w-4xl mx-auto w-full">
                    {/* Message History */}
                    {chatMessages.map((msg, index) => {
                      if (msg.role === 'user') {
                        return (
                          <div key={index} className="flex justify-end">
                            <div className="user-chat-bubble p-4 max-w-lg">
                              <p className="text-xs md:text-sm text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">
                                {msg.text}
                              </p>
                            </div>
                          </div>
                        )
                      }

                      return (
                        <div key={index} className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-full overflow-hidden border border-white/80 shrink-0 mt-1">
                            <div className="w-full h-full bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold text-xs">
                              AI
                            </div>
                          </div>

                          <div className="assistant-chat-card p-5 flex-1 space-y-2">
                            {/* 1. Lời giải đáp / Nội dung câu trả lời */}
                            <div
                              className="prose prose-xs md:prose-sm dark:prose-invert max-w-none leading-relaxed text-[var(--text-primary)]"
                              dangerouslySetInnerHTML={{ __html: marked.parse(msg.text || '') }}
                            />

                            {/* 2. Trích nguồn ở cuối lời khẳng định (Đã ẩn số trang theo yêu cầu) */}
                            {msg.sources && msg.sources.length > 0 && (
                              <div className="pt-2 flex items-center flex-wrap gap-2">
                                {(() => {
                                  const uniqueDocSources = []
                                  const seenDocs = new Set()
                                  for (const s of msg.sources) {
                                    const key = s.document_id || s.file_name
                                    if (!seenDocs.has(key)) {
                                      seenDocs.add(key)
                                      uniqueDocSources.push(s)
                                    }
                                  }
                                  return uniqueDocSources.map((s, sIdx) => {
                                    const isCurrentActive = chatSidebarOpen && (
                                      resolveDocId(s.document_id || s.file_name) === resolveDocId(chatActiveDocId) ||
                                      chatActiveDocName === s.file_name
                                    )
                                    return (
                                      <button
                                        key={sIdx}
                                        onClick={() => handleOpenSourceInSidebar(
                                          s.document_id || s.file_name,
                                          s.file_name,
                                          [s],
                                          msg.retrieved_chunks || [],
                                          s.page,
                                          msg.searchQuery || ''
                                        )}
                                        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border shadow-xs cursor-pointer select-none transition ${
                                          isCurrentActive
                                            ? 'bg-blue-600 text-white border-blue-600'
                                            : 'bg-zinc-800/90 hover:bg-zinc-700 text-zinc-200 border-zinc-700/60'
                                        }`}
                                        title={`Xem tài liệu: ${s.file_name}`}
                                      >
                                        <Icon name="globe" className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                                        <span className="truncate max-w-[280px] sm:max-w-[420px]">
                                          {formatSourceTitle(s.file_name)}
                                        </span>
                                      </button>
                                    )
                                  })
                                })()}
                              </div>
                            )}

                            {/* Thanh công cụ Copy & Chia sẻ câu trả lời */}
                            <div className="flex items-center gap-1 pt-2 text-zinc-400 select-none">
                              <button
                                onClick={() => handleCopyMessage(msg.text, msg.id || index)}
                                className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 hover:text-[var(--text-primary)] transition cursor-pointer flex items-center gap-1.5"
                                title={copiedMsgId === (msg.id || index) ? 'Đã sao chép' : 'Sao chép câu trả lời'}
                              >
                                <Icon
                                  name={copiedMsgId === (msg.id || index) ? 'check' : 'copy'}
                                  className={`w-4 h-4 ${copiedMsgId === (msg.id || index) ? 'text-emerald-500' : ''}`}
                                />
                                {copiedMsgId === (msg.id || index) && (
                                  <span className="text-[11px] text-emerald-500 font-medium">Đã sao chép</span>
                                )}
                              </button>

                              <button
                                onClick={() => handleShareMessage(msg.text)}
                                className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 hover:text-[var(--text-primary)] transition cursor-pointer"
                                title="Chia sẻ câu trả lời"
                              >
                                <Icon name="share" className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        </div>
                      )
                    })}

                    {/* Khi đang truy vấn: Cập nhật hiển thị tài liệu liên tục */}
                    {chatLoading && (
                      <div className="flex items-start gap-3">
                        <div className="w-8 h-8 rounded-full overflow-hidden border border-white/80 shrink-0 mt-1">
                          <div className="w-full h-full bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold text-xs">
                            AI
                          </div>
                        </div>

                        <div className="assistant-chat-card p-4 flex-1">
                          <div className="flex items-center gap-2.5 text-xs text-[var(--text-secondary)]">
                            <span className="relative flex h-2.5 w-2.5 shrink-0">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
                            </span>
                            <span className="text-[var(--text-muted)] font-normal">Đang truy vấn tài liệu:</span>
                            {(() => {
                              if (documents && documents.length > 0) {
                                const activeDoc = documents[queryingDocIndex % documents.length]
                                const docName = getDocName(activeDoc).replace(/\.[^/.]+$/, '').replace(/_/g, ' ')
                                return (
                                  <div className="flex items-center gap-1.5 min-w-0">
                                    <span
                                      key={queryingDocIndex}
                                      className="font-semibold text-blue-600 dark:text-blue-400 truncate max-w-[280px] sm:max-w-[420px] transition-all duration-200"
                                      title={docName}
                                    >
                                      {docName}
                                    </span>
                                    {documents.length > 1 && (
                                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-300 font-medium shrink-0">
                                        {(queryingDocIndex % documents.length) + 1}/{documents.length}
                                      </span>
                                    )}
                                  </div>
                                )
                              }
                              return (
                                <span className="font-semibold text-[var(--text-primary)]">
                                  {chatActiveDocName ? chatActiveDocName.replace(/\.[^/.]+$/, '').replace(/_/g, ' ') : 'Kho tài liệu tri thức'}
                                </span>
                              )
                            })()}
                          </div>
                        </div>
                      </div>
                    )}

                    <div ref={chatBottomRef} />
                  </div>

                  {/* Bottom Input Area - basic 1 dòng không tách 2 dòng */}
                  {/* Bottom Input Area - linh hoạt nhiều dòng: ChatGPT style */}
                  <div className="max-w-3xl xl:max-w-4xl mx-auto w-full pt-2">
                    {/* Dòng chữ cảnh báo AI ngay phía trên ô nhập */}
                    <div className="text-center pb-2 select-none">
                      <span className="text-[11.5px] text-[var(--text-muted)] font-normal">
                        Kết quả của trợ lý trí tuệ nhân tạo có thể chưa chính xác, kiểm chứng lại
                      </span>
                    </div>

                    {/* Khung nhập chat chuyển đổi thông minh: 1 dòng ban đầu, hộp khi đủ dài (như hình 1 & 2) */}
                    {!isInputMultiline ? (
                      /* DẠNG 1 DÒNG BAN ĐẦU */
                      <div className="w-full rounded-full border border-black/10 dark:border-white/10 bg-white/70 dark:bg-[#212121] shadow-md transition-all duration-200 px-2 sm:px-2.5 py-1.5 flex items-center gap-2 focus-within:border-zinc-400 dark:focus-within:border-zinc-500">
                        <button
                          type="button"
                          onClick={() => fileInputRef.current?.click()}
                          className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                          title="Tải lên tài liệu"
                        >
                          <Icon name="plus" className="w-4 h-4 stroke-[2.5]" />
                        </button>

                        <textarea
                          ref={chatInputRef}
                          rows={1}
                          value={chatInput}
                          onChange={e => setChatInput(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault()
                              handleSendChat()
                            }
                          }}
                          placeholder="Hỏi bất kỳ điều gì..."
                          spellCheck={false}
                          autoComplete="off"
                          className="flex-1 bg-transparent border-none outline-none text-xs sm:text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] resize-none leading-normal py-1 px-1 font-normal overflow-hidden h-6 min-h-[24px]"
                          style={{ height: '24px', minHeight: '24px', maxHeight: '24px' }}
                        />

                        <button
                          type="button"
                          className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                          title="Nhập bằng giọng nói"
                        >
                          <Icon name="mic" className="w-4 h-4" />
                        </button>

                        <button
                          type="button"
                          onClick={() => handleSendChat()}
                          disabled={chatLoading || !chatInput.trim()}
                          className={`w-8 h-8 rounded-full flex items-center justify-center transition shrink-0 ${
                            chatLoading
                              ? 'bg-zinc-900 text-white dark:bg-white dark:text-black shadow-xs cursor-pointer'
                              : chatInput.trim()
                              ? 'bg-zinc-900 text-white dark:bg-white dark:text-black shadow-xs cursor-pointer hover:opacity-90'
                              : 'bg-black/10 dark:bg-white/10 text-[var(--text-muted)] opacity-40 cursor-not-allowed'
                          }`}
                          title={chatLoading ? 'Đang xử lý...' : 'Gửi câu hỏi'}
                        >
                          {chatLoading ? (
                            <div className="w-3 h-3 bg-current rounded-xs" />
                          ) : (
                            <Icon name="arrowUp" className="w-4 h-4 stroke-[2.5]" />
                          )}
                        </button>
                      </div>
                    ) : (
                      /* DẠNG NHIỀU DÒNG (HÌNH 1 & HÌNH 2: TỰ CO GIÃN THEO VĂN BẢN, TỐI ĐA 280PX KÈM SCROLL) */
                      <div className="w-full rounded-3xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-[#212121] shadow-lg transition-all duration-200 p-3 sm:p-3.5 flex flex-col focus-within:border-zinc-400 dark:focus-within:border-zinc-500 animate-in fade-in-50 duration-150">
                        <textarea
                          ref={chatInputRef}
                          value={chatInput}
                          onChange={e => setChatInput(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault()
                              handleSendChat()
                            }
                          }}
                          placeholder="Hỏi bất kỳ điều gì..."
                          spellCheck={false}
                          autoComplete="off"
                          className="w-full bg-transparent border-none outline-none text-xs sm:text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] resize-none leading-relaxed px-1.5 py-1 overflow-y-auto"
                          style={{ minHeight: '54px', maxHeight: '280px' }}
                        />

                        <div className="flex items-center justify-between pt-2 px-1">
                          <button
                            type="button"
                            onClick={() => fileInputRef.current?.click()}
                            className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                            title="Tải lên tài liệu"
                          >
                            <Icon name="plus" className="w-4 h-4 stroke-[2.5]" />
                          </button>

                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition shrink-0 cursor-pointer"
                              title="Nhập bằng giọng nói"
                            >
                              <Icon name="mic" className="w-4 h-4" />
                            </button>

                            <button
                              type="button"
                              onClick={() => handleSendChat()}
                              disabled={chatLoading || !chatInput.trim()}
                              className={`w-8 h-8 rounded-full flex items-center justify-center transition shrink-0 ${
                                chatLoading
                                  ? 'bg-zinc-900 text-white dark:bg-white dark:text-black shadow-xs cursor-pointer'
                                  : chatInput.trim()
                                  ? 'bg-zinc-900 text-white dark:bg-white dark:text-black shadow-xs cursor-pointer hover:opacity-90'
                                  : 'bg-black/10 dark:bg-white/10 text-[var(--text-muted)] opacity-40 cursor-not-allowed'
                              }`}
                              title={chatLoading ? 'Đang xử lý...' : 'Gửi câu hỏi'}
                            >
                              {chatLoading ? (
                                <div className="w-3 h-3 bg-current rounded-xs" />
                              ) : (
                                <Icon name="arrowUp" className="w-4 h-4 stroke-[2.5]" />
                              )}
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Document Viewer Right Sidebar (Chỉ hiển thị 1 tài liệu 1 lần & bôi đậm các ý được truy vấn chính xác) */}
              {chatSidebarOpen && (
                <div className="w-[420px] lg:w-[480px] shrink-0 border-l border-black/5 dark:border-white/10 h-full flex flex-col bg-white/70 dark:bg-[#121316] backdrop-blur-xl overflow-hidden shadow-lg animate-in slide-in-from-right duration-200">
                  {/* Sidebar Header - 1 Tài liệu duy nhất */}
                  <div className="p-3 border-b border-black/5 dark:border-white/10 flex items-center justify-between shrink-0">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <Icon name="fileText" className="w-4 h-4 text-blue-500 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <span className="text-xs font-bold text-[var(--text-primary)] truncate block" title={chatActiveDocName || 'Tài liệu trích dẫn'}>
                          {chatActiveDocName || 'Tài liệu trích dẫn'}
                        </span>
                        {chatActiveQuery && (
                          <span className="text-[10px] text-[var(--text-muted)] truncate block">
                            Ý truy vấn: <strong className="text-amber-500 dark:text-amber-400 font-semibold">{chatActiveQuery}</strong>
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0 ml-2">
                      {chatDocBlobUrl && (
                        <button
                          onClick={() => window.open(chatDocBlobUrl, '_blank')}
                          className="circle-btn w-6 h-6"
                          title="Mở tài liệu trong tab mới"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3 h-3">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                            <polyline points="15 3 21 3 21 9" />
                            <line x1="10" y1="14" x2="21" y2="3" />
                          </svg>
                        </button>
                      )}
                      <button
                        onClick={() => setChatSidebarOpen(false)}
                        className="circle-btn w-6 h-6"
                        title="Đóng khung xem tài liệu"
                      >
                        <Icon name="x" className="w-3 h-3" />
                      </button>
                    </div>
                  </div>

                  {/* Tab bar: Ý chính bôi đậm vs Bản xem trước PDF */}
                  <div className="px-3 pt-2 pb-1.5 flex items-center justify-between border-b border-black/5 dark:border-white/10 shrink-0">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setChatSidebarTab('chunks')}
                        className={`px-2.5 py-1 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                          chatSidebarTab === 'chunks'
                            ? 'bg-blue-600 text-white shadow-2xs'
                            : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                        }`}
                      >
                        <span>Ý chính bôi đậm</span>
                        <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${chatSidebarTab === 'chunks' ? 'bg-white/20 text-white' : 'bg-black/10 dark:bg-white/10'}`}>
                          {filteredChunks.length}
                        </span>
                      </button>
                      <button
                        onClick={() => setChatSidebarTab('preview')}
                        className={`px-2.5 py-1 rounded-lg text-xs font-bold transition ${
                          chatSidebarTab === 'preview'
                            ? 'bg-blue-600 text-white shadow-2xs'
                            : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                        }`}
                      >
                        Bản xem trước PDF
                      </button>
                    </div>

                    {chatSidebarTab === 'preview' && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setChatDocUseNative(!chatDocUseNative)}
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold border transition ${
                            chatDocUseNative ? 'bg-blue-600 text-white border-blue-600' : 'text-[var(--text-muted)] border-black/10 dark:border-white/10 hover:text-[var(--text-primary)]'
                          }`}
                          title="Chuyển đổi giữa Trình đọc Canvas và Trình đọc trực tiếp"
                        >
                          {chatDocUseNative ? 'Canvas' : 'Trực tiếp'}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Sidebar Content Area */}
                  <div className="flex-1 overflow-hidden p-2 relative flex flex-col">
                    {chatSidebarTab === 'chunks' ? (
                      /* Tab: Ý chính bôi đậm */
                      <div className="flex-1 overflow-y-auto space-y-3 p-1">
                        {filteredChunks.length === 0 ? (
                          <div className="p-8 text-center text-xs text-[var(--text-muted)] space-y-2">
                            <Icon name="fileText" className="w-8 h-8 opacity-30 mx-auto" />
                            <p>Không có đoạn trích nào cho tài liệu này.</p>
                          </div>
                        ) : (
                          filteredChunks.map((c, cIdx) => {
                            const meta = c.metadata || {}
                            const pageNo = meta.page || meta.page_start || c.page || 1
                            const chunkText = c.content || c.text || c.snippet || ''

                            return (
                              <div
                                key={cIdx}
                                className="p-3.5 rounded-xl bg-black/5 dark:bg-white/[0.04] border border-black/5 dark:border-white/10 hover:border-amber-500/40 transition space-y-2"
                              >
                                <div className="flex items-center justify-between text-[11px] pb-1 border-b border-black/5 dark:border-white/5">
                                  <div className="flex items-center gap-1.5">
                                    <span className="font-bold text-amber-500 dark:text-amber-400">
                                      Đoạn #{cIdx + 1}
                                    </span>
                                    <span className="text-[var(--text-muted)]">• Trang {pageNo}</span>
                                    {meta.chunk_type && (
                                      <span className="px-1.5 py-0.2 rounded text-[10px] bg-blue-500/10 text-blue-500 font-medium">
                                        {meta.chunk_type}
                                      </span>
                                    )}
                                  </div>
                                  <button
                                    onClick={() => {
                                      setChatDocPage(Number(pageNo))
                                      setChatSidebarTab('preview')
                                    }}
                                    className="text-[10px] font-semibold text-blue-500 hover:text-blue-400 hover:underline flex items-center gap-1 cursor-pointer"
                                    title={`Xem trang ${pageNo} trên PDF`}
                                  >
                                    <Icon name="fileText" className="w-3 h-3" />
                                    <span>Xem trên PDF</span>
                                  </button>
                                </div>
                                <div className="text-xs text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap select-text">
                                  {highlightKeywords(chunkText, queryKeywords)}
                                </div>
                              </div>
                            )
                          })
                        )}
                      </div>
                    ) : (
                      /* Tab: Bản xem trước PDF */
                      chatDocBlobUrl ? (
                        (chatDocError || chatDocUseNative) ? (
                          <iframe
                            src={`${chatDocBlobUrl}#page=${chatDocPage}&toolbar=1&navpanes=0`}
                            title="Bản xem trước PDF"
                            className="w-full h-full rounded-lg border-0"
                            style={{ minHeight: '100%', minWidth: '100%' }}
                          />
                        ) : (
                          <div className="w-full h-full overflow-auto flex flex-col items-center bg-zinc-100 dark:bg-zinc-900 rounded-xl p-2">
                            {/* Page navigation bar */}
                            <div className="w-full flex items-center justify-between pb-2 mb-2 border-b border-black/5 dark:border-white/10 px-1">
                              <span className="text-[11px] font-medium text-[var(--text-secondary)]">
                                Trang {chatDocPage} / {chatDocNumPages || 1}
                              </span>
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => setChatDocPage(p => Math.max(1, p - 1))}
                                  disabled={chatDocPage <= 1}
                                  className="circle-btn w-6 h-6 disabled:opacity-40"
                                  title="Trang trước"
                                >
                                  <Icon name="chevronLeft" className="w-3 h-3" />
                                </button>
                                <button
                                  onClick={() => setChatDocPage(p => Math.min(chatDocNumPages || 1, p + 1))}
                                  disabled={chatDocPage >= (chatDocNumPages || 1)}
                                  className="circle-btn w-6 h-6 disabled:opacity-40"
                                  title="Trang sau"
                                >
                                  <Icon name="chevronRight" className="w-3 h-3" />
                                </button>
                              </div>
                            </div>
                            <div className="flex-1 overflow-auto flex items-center justify-center">
                              <Document
                                file={chatDocBlobUrl}
                                onLoadSuccess={({ numPages: n }) => {
                                  setChatDocNumPages(n)
                                  setChatDocError(false)
                                }}
                                onLoadError={(err) => {
                                  console.warn('react-pdf in chat sidebar failed, fallback to native iframe:', err)
                                  setChatDocError(true)
                                }}
                                loading={
                                  <div className="flex flex-col items-center gap-2 py-8">
                                    <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                                    <span className="text-xs text-[var(--text-muted)]">Đang tải PDF...</span>
                                  </div>
                                }
                                error={
                                  <div className="flex flex-col items-center gap-2 p-4 text-center">
                                    <span className="text-xs text-[var(--text-muted)]">Đang chuyển sang chế độ đọc trực tiếp...</span>
                                  </div>
                                }
                                className="shadow-md rounded overflow-hidden"
                              >
                                <Page pageNumber={chatDocPage} scale={0.9} customTextRenderer={customTextRenderer} />
                              </Document>
                            </div>
                          </div>
                        )
                      ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-[var(--text-muted)]">
                          {chatDocLoading ? (
                            <div className="flex flex-col items-center gap-2">
                              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                              <span className="text-xs">Đang tải bản xem trước tài liệu...</span>
                            </div>
                          ) : (
                            <div className="space-y-3">
                              <Icon name="fileText" className="w-8 h-8 opacity-40 mx-auto" />
                              <p className="text-xs">Tài liệu chưa sẵn sàng hoặc không có bản xem trước.</p>
                            </div>
                          )}
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ═══ VIEW B: QUẢN LÝ DOCUMENT (PREVIEW & TRÍCH XUẤT) ═══ */}
        {mainMode === 'documents' && (
          <div className="flex-1 flex flex-col h-full overflow-hidden">
            {/* Header Document Management */}
            <header className="h-12 px-5 border-b border-black/5 dark:border-white/10 flex items-center justify-between shrink-0 pl-14 sm:pl-5">
              <div className="flex items-center gap-2">
                <Icon name="folder" className="w-4 h-4 text-blue-600" />
                <span className="text-sm font-bold text-[var(--text-primary)] truncate max-w-md">
                  {currentDoc ? getDocName(currentDoc) : 'Quản lý Tài liệu'}
                </span>
                {currentDoc && (
                  <span className="text-[11px] text-[var(--text-muted)]">
                    ({formatFileSize(currentDoc.size_bytes)})
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-3 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition flex items-center gap-1"
                >
                  <Icon name="plus" className="w-3.5 h-3.5" />
                  Nạp file mới
                </button>
                <button
                  onClick={() => { setMainMode('chat'); pushHash('chat', activeConvId) }}
                  className="px-3 py-1 rounded-lg border border-black/10 dark:border-white/10 text-xs font-semibold text-[var(--text-primary)] hover:bg-black/5 dark:hover:bg-white/10 transition"
                >
                  Quay lại Chat
                </button>
              </div>
            </header>

            {/* Body */}
            {!currentDoc ? (
              /* Trạng thái CHƯA CHỌN TÀI LIỆU */
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                <div className="w-16 h-16 rounded-2xl bg-blue-500/10 text-blue-600 flex items-center justify-center mb-4 border border-blue-500/20 shadow-sm">
                  <Icon name="fileText" className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-bold text-[var(--text-primary)] mb-2">
                  Chưa chọn tài liệu
                </h3>
                <p className="text-xs text-[var(--text-muted)] max-w-md mb-6 leading-relaxed">
                  Vui lòng chọn một tài liệu từ thanh bên trái hoặc tải tệp mới lên để xem bản xem trước PDF và kết quả trích xuất cấu trúc Markdown / Chunks.
                </p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs transition shadow-sm flex items-center gap-1.5"
                >
                  <Icon name="plus" className="w-3.5 h-3.5" />
                  Tải lên tài liệu mới
                </button>
              </div>
            ) : (currentDoc.status === 'queued' || currentDoc.status === 'processing') ? (
              /* Trang thai dang xu ly */
              <div className="flex-1 flex items-center justify-center p-8">
                <div className="w-full max-w-lg">
                  <div style={{
                    background: 'linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(139,92,246,0.08) 50%, rgba(59,130,246,0.12) 100%)',
                    border: '1px solid rgba(139,92,246,0.3)',
                    borderRadius: '24px',
                    padding: '36px 32px',
                    backdropFilter: 'blur(20px)',
                    boxShadow: '0 0 60px rgba(99,102,241,0.15), 0 0 120px rgba(139,92,246,0.08)',
                    position: 'relative',
                    overflow: 'hidden'
                  }}>
                    {/* Luon sang ngang */}
                    <div style={{
                      position: 'absolute', inset: 0,
                      background: 'linear-gradient(90deg, transparent 0%, rgba(139,92,246,0.06) 50%, transparent 100%)',
                      animation: 'extractSweep 2.4s ease-in-out infinite',
                      borderRadius: '24px',
                      pointerEvents: 'none'
                    }} />

                    {/* Phan tram lon o giua */}
                    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '20px' }}>
                      <div style={{ position: 'relative', width: '96px', height: '96px' }}>
                        <div style={{
                          position: 'absolute', inset: '-18px',
                          borderRadius: '50%',
                          border: '1.5px solid rgba(139,92,246,0.25)',
                          animation: 'extractPulse 2.2s ease-out infinite'
                        }} />
                        <div style={{
                          position: 'absolute', inset: '-9px',
                          borderRadius: '50%',
                          border: '1.5px solid rgba(139,92,246,0.4)',
                          animation: 'extractPulse 2.2s ease-out infinite 0.5s'
                        }} />
                        <div style={{
                          width: '96px', height: '96px',
                          borderRadius: '50%',
                          background: 'linear-gradient(135deg, #6366f1, #8b5cf6, #3b82f6)',
                          display: 'flex', flexDirection: 'column',
                          alignItems: 'center', justifyContent: 'center',
                          boxShadow: '0 0 32px rgba(139,92,246,0.55)',
                          gap: '0px'
                        }}>
                          <span style={{ fontSize: '26px', fontWeight: 800, color: '#fff', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
                            {currentDoc.progress || 0}%
                          </span>
                          <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.75)', fontWeight: 600, letterSpacing: '0.05em', marginTop: '2px' }}>
                            hoàn thành
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Ten file va trang thai */}
                    <div style={{ textAlign: 'center', marginBottom: '22px', position: 'relative', zIndex: 1 }}>
                      <div style={{
                        display: 'inline-flex', alignItems: 'center', gap: '7px',
                        padding: '5px 14px', borderRadius: '999px',
                        background: 'rgba(139,92,246,0.15)',
                        border: '1px solid rgba(139,92,246,0.3)',
                        marginBottom: '10px'
                      }}>
                        <div style={{
                          width: '6px', height: '6px', borderRadius: '50%',
                          background: '#8b5cf6',
                          animation: 'extractBlink 1s ease-in-out infinite'
                        }} />
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#a78bfa', letterSpacing: '0.06em' }}>
                          {currentDoc.status === 'queued'
                            ? 'Đang chờ đến lượt'
                            : (currentDoc.progress_stage || 'Đang xử lý...')}
                        </span>
                      </div>
                      <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', margin: 0, marginBottom: '4px' }}>
                        {getDocName(currentDoc)}
                      </h3>
                      <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>
                        {currentDoc.status === 'queued'
                          ? 'Tệp đang xếp hàng chờ xử lý tuần tự (hệ thống xử lý từng tệp để tối ưu CPU/RAM), sẽ tự động bắt đầu ngay khi tệp trước hoàn thành.'
                          : 'Hệ thống đang đọc và xử lý nội dung tài liệu, vui lòng chờ một chút'}
                      </p>
                    </div>

                    {/* Cac buoc xu ly */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', position: 'relative', zIndex: 1 }}>
                      {[
                        {
                          num: 1,
                          label: 'Mở và kiểm tra tệp',
                          desc: 'Kiểm tra định dạng, dung lượng',
                          pct: 10,
                          prev: 0
                        },
                        {
                          num: 2,
                          label: 'Đọc nội dung từng trang',
                          desc: (currentDoc.progress >= 10 && currentDoc.progress < 60 && currentDoc.progress_stage)
                            ? currentDoc.progress_stage
                            : (currentDoc.progress >= 60 ? 'Đã nhận diện xong toàn bộ các trang' : 'Nhận diện chữ viết & OCR từng trang'),
                          pct: 60,
                          prev: 10
                        },
                        {
                          num: 3,
                          label: 'Cắt nhỏ thành từng đoạn',
                          desc: (currentDoc.progress >= 60 && currentDoc.progress < 88 && currentDoc.progress_stage)
                            ? currentDoc.progress_stage
                            : (currentDoc.progress >= 88 ? 'Đã phân tích ngữ nghĩa và cấu trúc xong' : 'Chia tài liệu, phân tích ngữ nghĩa AI'),
                          pct: 88,
                          prev: 60
                        },
                        {
                          num: 4,
                          label: 'Lưu vào cơ sở dữ liệu',
                          desc: currentDoc.progress >= 95 ? 'Đã lưu trữ và sẵn sàng tìm kiếm' : 'Lưu kết quả, sẵn sàng trả lời câu hỏi',
                          pct: 95,
                          prev: 88
                        }
                      ].map((step, i) => {
                        const prog = currentDoc.progress || 0
                        const isDone = prog >= step.pct
                        const isActive = !isDone && prog >= step.prev
                        return (
                          <div key={i} style={{
                            display: 'flex', alignItems: 'center', gap: '12px',
                            padding: '9px 13px',
                            borderRadius: '11px',
                            background: isDone
                              ? 'rgba(99,102,241,0.12)'
                              : isActive
                                ? 'rgba(139,92,246,0.08)'
                                : 'rgba(255,255,255,0.03)',
                            border: `1px solid ${isDone ? 'rgba(99,102,241,0.3)' : isActive ? 'rgba(139,92,246,0.2)' : 'rgba(255,255,255,0.05)'}`,
                            transition: 'all 0.4s ease'
                          }}>
                            {/* So thu tu */}
                            <div style={{
                              width: '24px', height: '24px', borderRadius: '50%', flexShrink: 0,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              background: isDone ? '#6366f1' : isActive ? 'rgba(139,92,246,0.3)' : 'rgba(255,255,255,0.06)',
                              fontSize: '11px', fontWeight: 800,
                              color: isDone ? '#fff' : isActive ? '#c4b5fd' : 'rgba(255,255,255,0.3)',
                              transition: 'all 0.4s ease'
                            }}>
                              {isDone ? (
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ width: '12px', height: '12px' }}>
                                  <polyline points="20 6 9 17 4 12" />
                                </svg>
                              ) : step.num}
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <p style={{ margin: 0, fontSize: '12px', fontWeight: 600, color: isDone ? '#c4b5fd' : isActive ? 'var(--text-primary)' : 'var(--text-muted)', transition: 'color 0.4s' }}>
                                {step.label}
                              </p>
                              <p style={{ margin: 0, fontSize: '10px', color: 'var(--text-muted)', marginTop: '1px' }}>
                                {step.desc}
                              </p>
                            </div>
                            {/* Mini bar */}
                            {isActive && (
                              <div style={{ width: '40px', height: '3px', borderRadius: '2px', background: 'rgba(139,92,246,0.15)', overflow: 'hidden', flexShrink: 0 }}>
                                <div style={{ height: '100%', background: 'linear-gradient(90deg, #6366f1, #8b5cf6)', borderRadius: '2px', animation: 'extractBar 1.6s ease-in-out infinite' }} />
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>

                    {/* Thanh tien trinh tong the */}
                    <div style={{ marginTop: '18px', position: 'relative', zIndex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Tiến trình xử lý</span>
                        <span style={{ fontSize: '10px', fontWeight: 700, color: '#a78bfa' }}>{currentDoc.progress || 0}%</span>
                      </div>
                      <div style={{ height: '5px', borderRadius: '3px', background: 'rgba(139,92,246,0.15)', overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          width: `${currentDoc?.progress || 0}%`,
                          background: 'linear-gradient(90deg, #6366f1, #8b5cf6, #3b82f6)',
                          borderRadius: '3px',
                          transition: 'width 0.8s ease'
                        }} />
                      </div>
                      <p style={{ textAlign: 'center', fontSize: '10px', color: 'var(--text-muted)', marginTop: '8px' }}>
                        Tự động cập nhật mỗi 2 giây
                      </p>
                    </div>
                  </div>

                  <style>{`
                    @keyframes extractSweep {
                      0% { transform: translateX(-100%); }
                      100% { transform: translateX(200%); }
                    }
                    @keyframes extractPulse {
                      0% { transform: scale(1); opacity: 0.7; }
                      100% { transform: scale(2.1); opacity: 0; }
                    }
                    @keyframes extractBlink {
                      0%, 100% { opacity: 1; } 50% { opacity: 0.25; }
                    }
                    @keyframes extractBar {
                      0% { width: 0%; margin-left: 0%; }
                      50% { width: 70%; margin-left: 0%; }
                      100% { width: 0%; margin-left: 100%; }
                    }
                  `}</style>
                </div>
              </div>
            ) : currentDoc.status === 'failed' ? (
              /* Trang thai that bai */
              <div className="flex-1 flex items-center justify-center p-8">
                <div style={{
                  maxWidth: '440px', width: '100%',
                  background: 'linear-gradient(135deg, rgba(239,68,68,0.08) 0%, rgba(220,38,38,0.05) 100%)',
                  border: '1px solid rgba(239,68,68,0.25)',
                  borderRadius: '20px',
                  padding: '36px 28px',
                  textAlign: 'center'
                }}>
                  <div style={{
                    width: '64px', height: '64px', borderRadius: '50%',
                    background: 'rgba(239,68,68,0.12)',
                    border: '1px solid rgba(239,68,68,0.3)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    margin: '0 auto 20px'
                  }}>
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '28px', height: '28px' }}>
                      <circle cx="12" cy="12" r="10" />
                      <line x1="15" y1="9" x2="9" y2="15" />
                      <line x1="9" y1="9" x2="15" y2="15" />
                    </svg>
                  </div>
                  <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#ef4444', marginBottom: '8px' }}>Đọc tài liệu không thành công</h3>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', lineHeight: 1.6 }}>
                    {getDocName(currentDoc)}
                  </p>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px', lineHeight: 1.6 }}>
                    Hệ thống gặp sự cố khi xử lý tài liệu này. Bạn có thể thử lại hoặc kiểm tra lại tệp.
                  </p>
                  {currentDoc.error_message && (
                    <p style={{ fontSize: '11px', color: '#f87171', background: 'rgba(239,68,68,0.08)', borderRadius: '8px', padding: '8px 12px', marginBottom: '20px', fontFamily: 'monospace', textAlign: 'left' }}>
                      {currentDoc.error_message}
                    </p>
                  )}
                  <button
                    onClick={async () => {
                      try {
                        await fetch(`/api/documents/${currentDoc.id}/extract`, { method: 'POST' })
                        await fetchDocuments()
                      } catch (e) { console.error(e) }
                    }}
                    style={{
                      padding: '10px 24px', borderRadius: '10px',
                      background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                      color: '#fff', fontWeight: 700, fontSize: '13px',
                      border: 'none', cursor: 'pointer'
                    }}
                  >
                    Thử lại
                  </button>
                </div>
              </div>
            ) : (
              /* Trạng thái ĐÃ CHỌN TÀI LIỆU & processed -> DUAL PANE */
              <div className="flex-1 flex overflow-hidden p-3 gap-3">
                {/* Left Sub-pane: PDF Viewer */}
                <div className="flex-1 rounded-2xl bg-white/60 dark:bg-black/20 border border-black/5 dark:border-white/10 flex flex-col overflow-hidden p-3 shadow-xs">
                  <div className="flex items-center justify-between pb-2 border-b border-black/5 dark:border-white/10 mb-2">
                    <span className="text-xs font-bold text-[var(--text-primary)]">
                      PDF Preview {(!pdfError && !useNativePdf && numPages) ? `• Trang ${currentPage} / ${numPages}` : ''}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {!pdfError && !useNativePdf && (
                        <>
                          <button
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage <= 1}
                            className="circle-btn w-6 h-6 disabled:opacity-40"
                            title="Trang trước"
                          >
                            <Icon name="chevronLeft" className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => setCurrentPage(p => Math.min(numPages || 1, p + 1))}
                            disabled={currentPage >= (numPages || 1)}
                            className="circle-btn w-6 h-6 disabled:opacity-40"
                            title="Trang sau"
                          >
                            <Icon name="chevronRight" className="w-3 h-3" />
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => setUseNativePdf(!useNativePdf)}
                        className={`px-2 py-0.5 rounded text-[11px] font-semibold border transition ${
                          useNativePdf ? 'bg-blue-600 text-white border-blue-600' : 'text-[var(--text-muted)] border-black/10 dark:border-white/10 hover:text-[var(--text-primary)]'
                        }`}
                        title="Chuyển đổi giữa Trình đọc Canvas và Trình đọc trực tiếp"
                      >
                        {useNativePdf ? 'Chế độ Canvas' : 'Chế độ trực tiếp'}
                      </button>
                      {pdfBlobUrl && (
                        <button
                          onClick={() => window.open(pdfBlobUrl, '_blank')}
                          className="circle-btn w-6 h-6"
                          title="Mở tài liệu trong tab mới"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3 h-3">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                            <polyline points="15 3 21 3 21 9" />
                            <line x1="10" y1="14" x2="21" y2="3" />
                          </svg>
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="flex-1 overflow-hidden flex items-center justify-center bg-zinc-100 dark:bg-zinc-900 rounded-xl p-1 relative">
                    {pdfBlobUrl ? (
                      (pdfError || useNativePdf) ? (
                        <iframe
                          src={`${pdfBlobUrl}#page=${currentPage}&toolbar=1&navpanes=0`}
                          title="Bản xem trước PDF"
                          className="w-full h-full rounded-lg border-0"
                          style={{ minHeight: '100%', minWidth: '100%' }}
                        />
                      ) : (
                        <div className="w-full h-full overflow-auto flex items-center justify-center p-2">
                          <Document
                            file={pdfBlobUrl}
                            onLoadSuccess={({ numPages: n }) => {
                              setNumPages(n)
                              setPdfError(false)
                            }}
                            onLoadError={(err) => {
                              console.warn('react-pdf render failed, fallback to native iframe:', err)
                              setPdfError(true)
                            }}
                            loading={
                              <div className="flex flex-col items-center gap-2 py-8">
                                <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                                <span className="text-xs text-[var(--text-muted)]">Đang tải PDF...</span>
                              </div>
                            }
                            error={
                              <div className="flex flex-col items-center gap-2 p-4 text-center">
                                <span className="text-xs text-[var(--text-muted)]">Đang chuyển sang chế độ đọc trực tiếp...</span>
                              </div>
                            }
                            className="shadow-md rounded overflow-hidden"
                          >
                            <Page pageNumber={currentPage} scale={pageScale} />
                          </Document>
                        </div>
                      )
                    ) : (
                      <p className="text-xs text-[var(--text-muted)]">
                        {pdfLoading ? 'Đang tải bản xem trước PDF...' : 'Đang chuẩn bị tệp PDF...'}
                      </p>
                    )}
                  </div>
                </div>

                {/* Right Sub-pane: Markdown & Chunks View */}
                <div className="flex-1 rounded-2xl bg-white/60 dark:bg-black/20 border border-black/5 dark:border-white/10 flex flex-col overflow-hidden p-3 shadow-xs">
                  <div className="flex items-center justify-between pb-2 border-b border-black/5 dark:border-white/10 mb-2">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setMdViewMode('rendered')}
                        className={`px-2.5 py-1 rounded-lg text-xs font-bold transition ${
                          mdViewMode === 'rendered' ? 'bg-blue-600 text-white shadow-2xs' : 'text-[var(--text-muted)]'
                        }`}
                      >
                        Đã định dạng .md
                      </button>
                      <button
                        onClick={() => setMdViewMode('raw')}
                        className={`px-2.5 py-1 rounded-lg text-xs font-bold transition ${
                          mdViewMode === 'raw' ? 'bg-blue-600 text-white shadow-2xs' : 'text-[var(--text-muted)]'
                        }`}
                      >
                        Thô .md
                      </button>
                      <button
                        onClick={() => setMdViewMode('chunks')}
                        className={`px-2.5 py-1 rounded-lg text-xs font-bold transition ${
                          mdViewMode === 'chunks' ? 'bg-blue-600 text-white shadow-2xs' : 'text-[var(--text-muted)]'
                        }`}
                      >
                        Chunks ({chunks.length})
                      </button>
                    </div>

                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(fullMarkdown)
                        setCopiedMd(true)
                        setTimeout(() => setCopiedMd(false), 2000)
                      }}
                      className="circle-btn w-6 h-6"
                      title={copiedMd ? 'Đã sao chép' : 'Sao chép Markdown'}
                    >
                      <Icon name={copiedMd ? 'check' : 'copy'} className="w-3 h-3" />
                    </button>
                  </div>

                  <div className="flex-1 overflow-y-auto p-3 rounded-xl bg-white/80 dark:bg-zinc-900/80 border border-black/5 text-xs">
                    {mdViewMode === 'chunks' ? (
                      <div className="space-y-2.5">
                        {chunks.length === 0 ? (
                          <p className="text-[var(--text-muted)] text-center py-12">Không có chunk nào.</p>
                        ) : (
                          chunks.map((c, idx) => (
                            <div key={idx} className="p-2.5 rounded-lg bg-black/5 dark:bg-white/5 border border-black/5">
                              <span className="text-[10px] font-bold text-blue-600 block mb-1">
                                Chunk #{c.chunk_index || idx + 1}
                              </span>
                              <p className="text-xs text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">
                                {c.content}
                              </p>
                            </div>
                          ))
                        )}
                      </div>
                    ) : fullMarkdown ? (
                      mdViewMode === 'rendered' ? (
                        <div
                          className="prose prose-xs dark:prose-invert max-w-none"
                          dangerouslySetInnerHTML={{ __html: marked.parse(fullMarkdown) }}
                        />
                      ) : (
                        <pre className="font-mono text-[11px] whitespace-pre-wrap">{fullMarkdown}</pre>
                      )
                    ) : (
                      <p className="text-[var(--text-muted)] text-center py-12">
                        {loadingExtraction ? 'Đang trích xuất văn bản từ tài liệu...' : 'Chưa có nội dung trích xuất.'}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

      </main>
    </div>
  )
}

const rootEl = document.getElementById('root')
if (rootEl) {
  createRoot(rootEl).render(<App />)
}
