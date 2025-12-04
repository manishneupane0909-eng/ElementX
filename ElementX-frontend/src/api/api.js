// src/api/api.js
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Helper function to get auth headers
const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Authorization': token ? `Bearer ${token}` : '',
  };
};

// Helper function to handle responses
const handleResponse = async (response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.json();
};

const api = {
  // Auth endpoints
  auth: {
    async register(userData) {
      const response = await fetch(`${API_URL}/api/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: userData.name,
          institution: userData.institution || '',
          email: userData.email,
          password: userData.password,
        }),
      });

      const data = await handleResponse(response);

      // Store token and user in localStorage
      if (data.token) {
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
      }

      return data;
    },

    async login(credentials) {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: credentials.email,
          password: credentials.password,
        }),
      });

      const data = await handleResponse(response);

      // Store token and user in localStorage
      if (data.token) {
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
      }

      return data;
    },

    logout() {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
    },

    getCurrentUser() {
      const userStr = localStorage.getItem('user');
      return userStr ? JSON.parse(userStr) : null;
    },

    getToken() {
      return localStorage.getItem('token');
    }
  },

  // Sample/calculation endpoints (mock for now - replace with real API later)
  samples: {
    async getAll() {
      // For now, return from localStorage
      // In production, this would call your backend endpoint
      const samplesStr = localStorage.getItem('samples');
      return samplesStr ? JSON.parse(samplesStr) : [];
    },

    async create(sampleData) {
      // For now, save to localStorage
      // In production, this would call your backend endpoint
      const samples = await this.getAll();
      const newSample = {
        ...sampleData,
        id: Date.now().toString(),
        userId: api.auth.getCurrentUser()?.id,
        createdAt: new Date().toISOString(),
      };
      samples.push(newSample);
      localStorage.setItem('samples', JSON.stringify(samples));
      return newSample;
    },

    async delete(id) {
      // For now, delete from localStorage
      // In production, this would call your backend endpoint
      const samples = await this.getAll();
      const filtered = samples.filter(s => s.id !== id);
      localStorage.setItem('samples', JSON.stringify(filtered));
      return { success: true };
    }
  },

  // XRD upload endpoint
  xrd: {
    async upload(file, sampleId = null, notes = null) {
      const formData = new FormData();
      formData.append('file', file);
      if (sampleId) formData.append('sampleId', sampleId);
      if (notes) formData.append('notes', notes);

      const response = await fetch(`${API_URL}/api/xrd/upload`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });

      return handleResponse(response);
    }
  },

  // Magnetic data upload endpoint
  magnetic: {
    async upload(file, measurementType = 'M-H', sampleId = null, notes = null) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('measurementType', measurementType);
      if (sampleId) formData.append('sampleId', sampleId);
      if (notes) formData.append('notes', notes);

      const response = await fetch(`${API_URL}/api/magnetic/upload`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });

      return handleResponse(response);
    }
  },

  // Health check
  async healthCheck() {
    const response = await fetch(`${API_URL}/health`);
    return handleResponse(response);
  }
};

export default api;