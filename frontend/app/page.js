// frontend/app/page.js
'use client'; // This is required for using hooks like useState and useEffect

import { useEffect, useState } from 'react';

export default function Home() {
  const [backendMessage, setBackendMessage] = useState('');
  const [status, setStatus] = useState('connecting');

  useEffect(() => {
    // Fetch the message from our FastAPI backend
    fetch('http://localhost:8000/api/health')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }
        return response.json();
      })
      .then((data) => {
        setBackendMessage(data.message);
        setStatus('connected');
      })
      .catch((error) => {
        console.error('Failed to fetch from backend:', error);
        setBackendMessage('Failed to connect to the backend.');
        setStatus('error');
      });
  }, []); // The empty array ensures this effect runs only once on component mount

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold mb-4">Enigma Poker</h1>
      <div className="text-lg">
        <p>
          Backend Status: 
          <span className={status === 'connected' ? 'text-green-500' : 'text-red-500'}>
            {' '}{status}
          </span>
        </p>
        <p>Message: <span className="font-mono bg-gray-200 p-1 rounded">{backendMessage}</span></p>
      </div>
    </main>
  );
}