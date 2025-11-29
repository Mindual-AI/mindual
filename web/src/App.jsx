import { useMemo, useState, useEffect } from 'react'
import './App.css'

// 백엔드 RAG API 엔드포인트, 캘린더 엔드포인트
const RAG_API_URL = 'http://127.0.0.1:5500/rag/query'
const CAL_API_URL = 'http://localhost:5500/calendar/events'

function App() {
  const formatISODate = (date) => {
    const year = date.getFullYear()
    const month = `${date.getMonth() + 1}`.padStart(2, '0')
    const day = `${date.getDate()}`.padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  const today = useMemo(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), now.getDate())
  }, [])

  const initialMessages = useMemo(() => [], [])

  const [messages, setMessages] = useState(initialMessages)
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)

  const calendar = useMemo(() => {
    const year = today.getFullYear()
    const monthIndex = today.getMonth()

    const firstDay = new Date(year, monthIndex, 1)
    const startWeekday = firstDay.getDay()
    const daysInMonth = new Date(year, monthIndex + 1, 0).getDate()

    const cells = []
    for (let i = 0; i < startWeekday; i += 1) {
      cells.push(null)
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const currentDate = new Date(year, monthIndex, day)
      cells.push({
        key: formatISODate(currentDate),
        label: day,
        isToday: day === today.getDate()
      })
    }

    while (cells.length % 7 !== 0) {
      cells.push(null)
    }

    return {
      label: `${year}년 ${monthIndex + 1}월`,
      cells
    }
  }, [today])

  const [calendarEvents, setCalendarEvents] = useState([])

  // 1) 함수로 분리
const fetchEvents = async () => {
  try {
    const resp = await fetch(`${CAL_API_URL}?limit=10`)
    if (!resp.ok) {
      throw new Error(`Calendar API error: ${resp.status}`)
    }
    const data = await resp.json()
    setCalendarEvents(data.events || [])
  } catch (err) {
    console.error('캘린더 이벤트 조회 실패:', err)
    setCalendarEvents([])
  }
}

// 2) 마운트 시 한 번 호출
useEffect(() => {
  fetchEvents()
}, [])

  const handleSubmit = async (event) => {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || loading) return

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      name: '나',
      content: trimmed
    }

    setMessages((prev) => [...prev, userMessage])
    setQuestion('')
    setLoading(true)

    try {
      const resp = await fetch(RAG_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ query: trimmed })
      })

      if (!resp.ok) {
        throw new Error(`RAG API error: ${resp.status}`)
      }

      const data = await resp.json()
      const answerText = data.answer ?? data.result ?? '응답을 가져오지 못했어요.'
      const sources = data.contexts ?? data.sources ?? []
      const intent = data.intent ?? 'rag'
      const isReminder = intent === 'reminder'

      let decoratedAnswer = answerText
      if (!isReminder && sources.length > 0) {
        const first = sources[0]
        const pageInfo = first.page ?? first.page_number
        if (pageInfo) {
          decoratedAnswer += `\n\n(참고: p.${pageInfo} 등 매뉴얼 내용 기반)`
        }
      }

      const agentMessage = {
        id: `agent-${Date.now()}`,
        role: 'agent',
        name: 'Mindual',
        content: decoratedAnswer,
        variant: isReminder ? 'reminder' : undefined,
      }

      setMessages((prev) => [...prev, agentMessage])
      if (isReminder) {
        await fetchEvents()
      }
    } catch (error) {
      console.error(error)
      const agentMessage = {
        id: `agent-${Date.now()}`,
        role: 'agent',
        name: 'Mindual',
        content:
          '죄송해요, RAG 서버에 연결하는 데 문제가 발생했습니다.\n서버 상태를 확인한 후 다시 시도해 주세요.'
      }
      setMessages((prev) => [...prev, agentMessage])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <div className="brand-bar">
        <div className="brand-title">MINDUAL</div>
        <div className="header-actions">
          <button type="button" className="primary ghost">
            메뉴얼
          </button>
          <button type="button" className="primary">사용자 설정</button>
        </div>
      </div>
      <main className="layout">
        <section className="panel chat-panel">
          <header>
            <div className="chat-title">
              <h1>질문하기</h1>
              <p className="subtitle">
                RAG 기반 에이전트 MINDUAL에게 궁금한 것을 전달하고 사용법에 대한 답변을 한눈에
                확인하세요.
              </p>
            </div>
            <span className="tag">{loading ? 'Thinking...' : 'Live'}</span>
          </header>

          <div className="chat-window">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`chat-row ${message.role} ${message.variant ?? ''}`}
              >
                <div className="avatar">
                  {message.role === 'agent' ? '🤖' : '🙂'}
                </div>
                <div className="bubble">
                  <div className="bubble-header">
                    <span className="name">{message.name}</span>
                    {message.role === 'agent' && message.variant !== 'reminder' && (
                      <span className="source">지식 베이스 · 최신 매뉴얼</span>
                    )}
                  </div>
                  <p>
                    {message.content.split('\n').map((line, index) => (
                      <span key={index}>
                        {line}
                        <br />
                      </span>
                    ))}
                  </p>
                </div>
              </div>
            ))}

            {messages.length === 0 && (
              <div className="chat-empty-hint">
                아직 대화가 없어요. 아래 입력창에 질문을 남기면 매뉴얼 기반으로 답변해 드릴게요.
              </div>
            )}
          </div>

          <form className="input-area" onSubmit={handleSubmit}>
            <label htmlFor="question" className="sr-only">
              사용자 질문
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="질문을 입력하세요. ( ex. 제품 A의 필터 교체 주기를 알려줘. )"
              disabled={loading}
            />
            <div className="form-actions">
              <button type="button" className="secondary" disabled>
                지식 베이스 연결됨
              </button>
              <button type="submit" className="primary" disabled={loading}>
                {loading ? '응답 생성 중...' : '전송'}
              </button>
            </div>
          </form>
        </section>

        {/* 오른쪽 패널은 그대로 유지 */}
        <aside className="panel assistant-panel">
          <div className="info-card">
            <h3>연결된 문서</h3>
            <ul>
              <li>
                LG_Purifier 공기청정기 사용설명서
                <span className="pill success">동기화</span>
              </li>
              <li>
                LG 에어컨 청소 가이드
                <span className="pill warning">업데이트 필요</span>
              </li>
              <li>
                서비스 FAQ.xlsx
                <span className="pill info">RAG 캐시</span>
              </li>
            </ul>
          </div>

          {/*<div className="info-card">*/}
          {/*  <h3>자동화 워크플로</h3>*/}
          {/*  <div className="workflow">*/}
          {/*    <div className="workflow-step">*/}
          {/*      <span className="icon">🔍</span>*/}
          {/*      <div>*/}
          {/*        <p className="label">임베딩 검색</p>*/}
          {/*        <p className="desc">질문과 유사한 문서를 Vector DB에서 조회</p>*/}
          {/*      </div>*/}
          {/*    </div>*/}
          {/*    <div className="workflow-step">*/}
          {/*      <span className="icon">🧠</span>*/}
          {/*      <div>*/}
          {/*        <p className="label">컨텍스트 생성</p>*/}
          {/*        <p className="desc">관련 문단을 조합해 LLM에 전달</p>*/}
          {/*      </div>*/}
          {/*    </div>*/}
          {/*    <div className="workflow-step">*/}
          {/*      <span className="icon">✅</span>*/}
          {/*      <div>*/}
          {/*        <p className="label">액션 실행</p>*/}
          {/*        <p className="desc">필요 시 리마인더, 티켓 생성 등 후속 작업 실행</p>*/}
          {/*      </div>*/}
          {/*    </div>*/}
          {/*  </div>*/}
          {/*</div>*/}

          <div className="info-card calendar-card">
            <div className="calendar-header">
              <div>
                <h3>캘린더</h3>
                <p className="calendar-subtitle">
                  Google Calendar API와 연동하여 최신 배포 일정을 자동으로 받아옵니다.
                </p>
              </div>
              <button type="button" className="primary ghost">
                Google Calendar 동기화
              </button>
            </div>
            <div className="calendar-meta">
              <span className="month-label">{calendar.label}</span>
              <span className="timezone">기준: Asia/Seoul</span>
            </div>

            <div className="weekday-grid">
              {['일', '월', '화', '수', '목', '금', '토'].map((weekday) => (
                <span key={weekday} className="weekday">
                  {weekday}
                </span>
              ))}
            </div>
            <div className="calendar-grid">
              {calendar.cells.map((cell, index) => {
                if (!cell) {
                  return <div key={`empty-${index}`} className="calendar-cell empty" />
                }

                const dailyEvents = calendarEvents.filter(
                  (event) => event.date === cell.key
                )

                return (
                  <div
                    key={cell.key}
                    className={`calendar-cell ${cell.isToday ? 'today' : ''} ${
                      dailyEvents.length ? 'has-event' : ''
                    }`}
                  >
                    <span className="day-number">{cell.label}</span>
                    {dailyEvents.length > 0 && <span className="event-dot" />}
                  </div>
                )
              })}
            </div>

            <div className="event-list">
              <h4>다가오는 일정</h4>
              <ul>
                {calendarEvents.map((event) => (
                  <li key={event.id}>
                    <div className="event-date">
                      {event.date.slice(5)} <span>{event.time}</span>
                    </div>
                    <div className="event-detail">
                      <p className="event-title">{event.title}</p>
                      <p className="event-location">{event.location}</p>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="api-note">
                연결 후에는 Google Calendar에서 승인한 이벤트만 표시되며, 오늘 날짜는
                보라색으로 강조됩니다.
              </p>
            </div>
          </div>
        </aside>
      </main>
    </div>
  )
}

export default App
