import React, { useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, addMonths, subMonths } from 'date-fns';
import { ChevronLeft, ChevronRight, Clock, CheckCircle2, AlertCircle } from 'lucide-react';
import { mockCalendarEvents } from '../lib/api';

export const CalendarPage: React.FC = () => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [events, setEvents] = useState(mockCalendarEvents);

  const [showAddModal, setShowAddModal] = useState(false);
  const [newEventTitle, setNewEventTitle] = useState('');
  const [newEventDate, setNewEventDate] = useState('');
  const [newEventType, setNewEventType] = useState('deadline');
  const [newEventStatus, setNewEventStatus] = useState('pending');

  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

  const nextMonth = () => setCurrentDate(addMonths(currentDate, 1));
  const prevMonth = () => setCurrentDate(subMonths(currentDate, 1));

  const getEventsForDay = (date: Date) => {
    return events.filter(event => isSameDay(new Date(event.date), date));
  };

  const handleAddEventSubmit = () => {
    if (!newEventTitle.trim() || !newEventDate) return;
    const newEvent = {
      id: Date.now(),
      title: newEventTitle,
      date: new Date(newEventDate).toISOString(),
      type: newEventType,
      status: newEventStatus
    };
    setEvents([...events, newEvent]);
    setShowAddModal(false);
    
    // Reset form
    setNewEventTitle('');
    setNewEventDate('');
    setNewEventType('deadline');
    setNewEventStatus('pending');
  };

  const exportCalendar = () => {
    let icsContent = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Society Compliance Copilot//Compliance Calendar//EN\n";
    events.forEach(event => {
      const date = new Date(event.date);
      const year = date.getUTCFullYear();
      const month = String(date.getUTCMonth() + 1).padStart(2, '0');
      const day = String(date.getUTCDate()).padStart(2, '0');
      const dateStr = `${year}${month}${day}`;
      
      icsContent += "BEGIN:VEVENT\n";
      icsContent += `UID:${event.id}-${dateStr}@societycopilot.local\n`;
      icsContent += `DTSTART;VALUE=DATE:${dateStr}\n`;
      icsContent += `SUMMARY:${event.title}\n`;
      icsContent += `DESCRIPTION:Status: ${event.status} | Type: ${event.type}\n`;
      icsContent += "END:VEVENT\n";
    });
    icsContent += "END:VCALENDAR";

    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'compliance_calendar.ics');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const StatusIcon = ({ status }: { status: string }) => {
    if (status === 'completed') return <CheckCircle2 size={14} className="text-green-500" />;
    if (status === 'overdue') return <AlertCircle size={14} className="text-red-500" />;
    return <Clock size={14} className="text-brand-500" />;
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto custom-scrollbar p-4 sm:p-8 bg-slate-50/50 dark:bg-background-dark">
      <div className="max-w-6xl mx-auto w-full">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Compliance Calendar</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">Track deadlines, audits, and society meetings.</p>
          </div>
          <div className="flex gap-2 mt-4 sm:mt-0">
            <button onClick={exportCalendar} className="btn-secondary px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">Export Calendar</button>
            <button onClick={() => setShowAddModal(true)} className="btn-primary px-4 py-2 bg-brand-500 hover:bg-brand-600 text-white rounded-lg transition-colors">Add Event</button>
          </div>
        </div>

        <div className="glass-panel rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800">
          {/* Calendar Header */}
          <div className="p-4 flex items-center justify-between border-b border-slate-200 dark:border-slate-800">
            <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100">
              {format(currentDate, 'MMMM yyyy')}
            </h2>
            <div className="flex gap-2">
              <button onClick={prevMonth} className="btn-icon"><ChevronLeft size={20} /></button>
              <button onClick={nextMonth} className="btn-icon"><ChevronRight size={20} /></button>
            </div>
          </div>

          {/* Calendar Grid */}
          <div className="grid grid-cols-7 gap-px bg-slate-200 dark:bg-slate-800">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
              <div key={day} className="bg-white dark:bg-slate-900 p-2 text-center text-sm font-semibold text-slate-500 uppercase tracking-wider">
                {day}
              </div>
            ))}
            
            {/* Empty slots for start of month offset */}
            {Array.from({ length: monthStart.getDay() }).map((_, i) => (
              <div key={`empty-${i}`} className="bg-slate-50 dark:bg-slate-900/50 min-h-[120px] p-2" />
            ))}

            {days.map(day => {
              const dayEvents = getEventsForDay(day);
              const isToday = isSameDay(day, new Date());
              return (
                <div key={day.toISOString()} className={`bg-white dark:bg-slate-900 min-h-[120px] p-2 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50`}>
                  <div className={`text-sm font-medium w-8 h-8 flex items-center justify-center rounded-full mb-2 ${isToday ? 'bg-brand-500 text-white' : 'text-slate-700 dark:text-slate-300'}`}>
                    {format(day, 'd')}
                  </div>
                  <div className="space-y-1.5">
                    {dayEvents.map(event => (
                      <div key={event.id} className="text-xs p-1.5 rounded-md border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 flex flex-col gap-1 cursor-pointer hover:border-brand-300 transition-colors">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-700 dark:text-slate-200 truncate">{event.title}</span>
                        </div>
                        <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-medium text-slate-500">
                          <StatusIcon status={event.status} /> {event.status}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Add Event Modal */}
        {showAddModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 w-full max-w-md shadow-2xl relative">
              <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-4">Add Compliance Event</h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Event Title</label>
                  <input 
                    type="text" 
                    value={newEventTitle} 
                    onChange={e => setNewEventTitle(e.target.value)} 
                    placeholder="e.g. Submit Audit Report" 
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm"
                  />
                </div>
                
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Date</label>
                  <input 
                    type="date" 
                    value={newEventDate} 
                    onChange={e => setNewEventDate(e.target.value)} 
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm"
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Type</label>
                    <select 
                      value={newEventType} 
                      onChange={e => setNewEventType(e.target.value)}
                      className="w-full px-3.5 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm"
                    >
                      <option value="deadline">Deadline</option>
                      <option value="compliance">Compliance</option>
                      <option value="event">Event</option>
                      <option value="meeting">Meeting</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Status</label>
                    <select 
                      value={newEventStatus} 
                      onChange={e => setNewEventStatus(e.target.value)}
                      className="w-full px-3.5 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm"
                    >
                      <option value="pending">Pending</option>
                      <option value="completed">Completed</option>
                      <option value="overdue">Overdue</option>
                    </select>
                  </div>
                </div>
              </div>
              
              <div className="flex gap-2 justify-end mt-6">
                <button 
                  onClick={() => setShowAddModal(false)} 
                  className="px-4 py-2 text-sm font-semibold rounded-lg border border-slate-200 dark:border-slate-800 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  Cancel
                </button>
                <button 
                  onClick={handleAddEventSubmit}
                  className="px-4 py-2 text-sm font-semibold rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition-colors"
                >
                  Save Event
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
