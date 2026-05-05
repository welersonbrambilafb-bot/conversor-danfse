/* ===================================================================
   posts.js — Lista mestre de artigos publicados no blog DANFSe.tools

   Como adicionar um novo artigo:
   1. Crie o arquivo HTML do artigo (ex: meu-artigo.html) na pasta blog/
   2. Adicione um objeto neste array com os campos abaixo
   3. Faça commit no GitHub e o site atualiza automaticamente

   Campos:
   - slug:     nome do arquivo HTML sem extensão (ex: "o-que-e-danfse")
   - category: rótulo curto (ex: "Conceitos", "Operacional", "Técnico")
   - title:    título completo do artigo
   - excerpt:  resumo curto (1-2 frases)
   - readTime: tempo estimado de leitura (ex: "6 min")
   - level:    "Iniciante", "Intermediário" ou "Avançado"
   - group:    "basico" | "tecnico" | "operacional"
   =================================================================== */
window.POSTS = [
  {
    "slug": "o-que-e-danfse",
    "category": "Conceitos",
    "title": "O que é DANFSe e qual a diferença para a NFS-e",
    "excerpt": "Entenda a relação entre o documento fiscal eletrônico (NFS-e) e sua representação visual em PDF (DANFSe), e por que os dois existem.",
    "readTime": "6 min",
    "level": "Iniciante",
    "group": "basico"
  }
];
