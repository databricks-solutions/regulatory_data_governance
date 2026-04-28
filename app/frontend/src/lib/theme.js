export const layerColors = {
  source: { bg: '#F0F0F5', border: '#7A7A8A', text: '#4A4A5A' },
  bronze: { bg: '#F0F0F5', border: '#7A7A8A', text: '#4A4A5A' },
  silver: { bg: '#E5F0F8', border: '#005CA9', text: '#003D73' },
  gold: { bg: '#FFF3E8', border: '#F37021', text: '#D35F1A' },
  output: { bg: '#FFF3E8', border: '#F37021', text: '#D35F1A' }
};

export const statusColors = {
  conforme: { bg: '#E8F5EC', color: '#1B8A3D', label: 'Conforme' },
  atencao: { bg: '#FFF3E8', color: '#D35F1A', label: 'Atenção' },
  nao_conforme: { bg: '#FDECEA', color: '#D32F2F', label: 'Não Conforme' },
  pendente: { bg: '#E5F0F8', color: '#0070AF', label: 'Pendente' },
  passed: { bg: '#E8F5EC', color: '#1B8A3D', label: 'Aprovado' },
  warning: { bg: '#FFF3E8', color: '#D35F1A', label: 'Alerta' },
  failed: { bg: '#FDECEA', color: '#D32F2F', label: 'Reprovado' },
  blocked: { bg: '#FDECEA', color: '#D32F2F', label: 'Bloqueado' }
};

export const dimensionNames = [
  'Acessibilidade', 'Acurácia', 'Adaptabilidade', 'Atualidade',
  'Completude', 'Consistência', 'Confidencialidade', 'Disponibilidade',
  'Granularidade', 'Rastreabilidade', 'Relevância', 'Conformidade'
];
