const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Authorization': token ? `Bearer ${token}` : '',
  };
};

const handleResponse = async (response) => {
  if (response.status === 401) {
    const errorData = await response.json().catch(() => ({}));
    const hadSession = !!localStorage.getItem('token');
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    // Only force a logout flow if we actually had a session (avoids hijacking login-failure messaging).
    if (hadSession && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('elementx:unauthorized'));
    }
    throw new Error(errorData.detail || 'Session expired — please log in again.');
  }
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.json();
};

const api = {
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

  samples: {
    async getAll() {
      const response = await fetch(`${API_URL}/api/samples`, {
        headers: getAuthHeaders(),
      });
      return handleResponse(response);
    },

    async getById(id) {
      const response = await fetch(`${API_URL}/api/samples/${id}`, {
        headers: getAuthHeaders(),
      });
      return handleResponse(response);
    },

    async create(sampleData) {
      const response = await fetch(`${API_URL}/api/samples`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: sampleData.name,
          formula: sampleData.formula,
          material_family: sampleData.material_family || 'mnal_tau',
          dopants: sampleData.dopants || [],
          synthesis: sampleData.synthesis || { method: 'arc_melt' },
          status: sampleData.status || 'planned',
          project_name: sampleData.project_name || 'RE-Free Magnets',
          stoichiometry: sampleData.stoichiometry || null,
        }),
      });
      return handleResponse(response);
    },

    async update(id, sampleData) {
      const payload = { ...sampleData };
      if (payload.outcome_label !== undefined) {
        payload.outcome_label = payload.outcome_label;
      }
      const response = await fetch(`${API_URL}/api/samples/${id}`, {
        method: 'PATCH',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      return handleResponse(response);
    },

    async delete(id) {
      const response = await fetch(`${API_URL}/api/samples/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      return handleResponse(response);
    },

    async recommend(id) {
      const response = await fetch(`${API_URL}/api/samples/${id}/recommend`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      return handleResponse(response);
    },

    async experimentBrief(id) {
      const response = await fetch(`${API_URL}/api/samples/${id}/experiment-brief`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      return handleResponse(response);
    },
  },

  ai: {
    async status() {
      const response = await fetch(`${API_URL}/api/ai/status`, {
        headers: getAuthHeaders(),
      });
      return handleResponse(response);
    },

    async parseSynthesis(notes) {
      const response = await fetch(`${API_URL}/api/ai/parse-synthesis`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ notes }),
      });
      return handleResponse(response);
    },

    async copilot(question, sampleId = null, projectName = null) {
      const response = await fetch(`${API_URL}/api/ai/copilot`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question,
          sample_id: sampleId || null,
          project_name: projectName || null,
        }),
      });
      return handleResponse(response);
    },
  },

  agent: {
    async status() {
      const response = await fetch(`${API_URL}/api/agent/status`, {
        headers: getAuthHeaders(),
      });
      return handleResponse(response);
    },

    async chat(message, sampleId = null, history = []) {
      const response = await fetch(`${API_URL}/api/agent/chat`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          sample_id: sampleId || null,
          history: history.slice(-6),
        }),
      });
      return handleResponse(response);
    },
  },

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

  async healthCheck() {
    const response = await fetch(`${API_URL}/health`);
    return handleResponse(response);
  },

  demo: {
    async bootstrap() {
      const response = await fetch(`${API_URL}/api/demo/bootstrap`, { method: 'POST' });
      return handleResponse(response);
    },

    async load(force = false) {
      const response = await fetch(`${API_URL}/api/demo/load`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ force }),
      });
      return handleResponse(response);
    },
  },
};

export default api;