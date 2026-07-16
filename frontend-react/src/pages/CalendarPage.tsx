import React, { useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, addMonths, subMonths } from 'date-fns';
import { ChevronLeft, ChevronRight, Clock, CheckCircle2, AlertCircle } from 'lucide-react';
import { mockCalendarEvents } from '../lib/api';

export const CalendarPage: React.FC = () => {
  const [currentDate, setCurrentDate] = useState(new Date());

  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

  const nextMonth = () => setCurrentDate(addMonths(currentDate, 1));
  const prevMonth = () => setCurrentDate(subMonths(currentDate, 1));

  const getEventsForDay = (date: Date) => {
    return mockCalendarEvents.filter(event => isSameDay(new Date(event.date), date));
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
            <button className="btn-secondary px-4 py-2">Export Calendar</button>
            <button className="btn-primary px-4 py-2">Add Event</button>
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
      </div>
    </div>
  );
};
